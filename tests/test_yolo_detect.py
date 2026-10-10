from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread, get_ident
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import torch
from ultralytics.engine.results import Results

from pipeworks.embedded import CudaAsync, YoloDetect
from pipeworks.embedded.stream_report import _stats, report_scope
from pipeworks.models import PipelineContext


def context(height=4, width=4):
    stream = torch.cuda.Stream()
    with torch.cuda.stream(stream):
        frame = torch.full((height * 3 // 2, width), 128, dtype=torch.uint8, device="cuda")
    return PipelineContext(frame=frame, pixel_format="NV12", cuda_stream=stream,
                           video_stream=SimpleNamespace(codec_context=SimpleNamespace(width=width, height=height)))


def detection_result(boxes=None):
    if boxes is None:
        boxes = torch.empty((0, 6), device="cuda")
    return Results(torch.zeros((640, 640, 3), device="cuda"), path="image", names={2: "car"}, boxes=boxes)


class YoloSettingsTests(unittest.TestCase):
    def test_optional_batch_parameter(self):
        self.assertFalse(YoloDetect(Path("model.pt")).batch)
        self.assertTrue(YoloDetect(Path("model.pt"), batch=True).batch)
        for value in (None, 1, 0, "true"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                YoloDetect(Path("model.pt"), batch=value)

    def test_configuration_and_validation(self):
        step = YoloDetect(Path("model.pt"))
        step.configure(SimpleNamespace(classes=[2], confidence=0.4, gpu_id=0, inference_interval_frame=3))
        self.assertEqual((step.classes, step.confidence, step.gpu_id, step.inference_interval_frame), ([2], 0.4, 0, 3))
        self.assertEqual(YoloDetect(Path("model.pt")).inference_interval_frame, 1)
        for config in (SimpleNamespace(classes=[True]), SimpleNamespace(classes=[-1]),
                       SimpleNamespace(confidence=0), SimpleNamespace(gpu_id=-1),
                       *(SimpleNamespace(inference_interval_frame=value) for value in (0, -1, True, 1.5, "3", None))):
            with self.subTest(config=config), self.assertRaises(ValueError):
                step.configure(config)

    def test_internal_async_and_timeout_are_removed(self):
        step = YoloDetect(Path("model.pt"))
        self.assertFalse(hasattr(step, "_worker"))
        self.assertFalse(hasattr(step, "_timeout_seconds"))


@unittest.skipUnless(torch.cuda.is_available(), "CUDA가 필요합니다.")
class YoloDetectTests(unittest.TestCase):
    def test_batch_mode_uses_existing_worker_and_interval(self):
        step = YoloDetect(Path("model.pt"), batch=True)
        step.configure(SimpleNamespace(classes=[2], confidence=.4, inference_interval_frame=3))
        frames = [context() for _ in range(7)]
        with patch("pipeworks.embedded.yolo_detect.infer", side_effect=["first", "fourth", "seventh"]) as infer:
            outputs = list(step.process(iter(frames)))
        self.assertEqual(outputs, frames)
        self.assertEqual([item.detections for item in outputs], ["first", None, None, "fourth", None, None, "seventh"])
        self.assertEqual(infer.call_count, 3)
        self.assertEqual(infer.call_args.args[2:], ([2], .4, 0))

    def test_legacy_batch_api_is_removed(self):
        import importlib.util
        from pipeworks import embedded
        self.assertFalse(hasattr(embedded, "YoloDetectBatch"))
        self.assertIsNone(importlib.util.find_spec("pipeworks.embedded.yolo_detect_batch"))

    def test_batch_records_queue_wait_and_inference_in_calling_scope(self):
        item = context()
        step = YoloDetect(Path("model.pt"), batch=True)

        def infer(*args, on_inference_complete, **kwargs):
            on_inference_complete(.012)
            return "detected"

        with patch("pipeworks.embedded.yolo_detect.infer", side_effect=infer), patch(
            "pipeworks.embedded.yolo_detect.record_stage"
        ) as record, report_scope():
            stats = _stats()
            list(step.process(iter([item])))
            self.assertEqual(stats.snapshot.completed_inferences, 1)
            self.assertAlmostEqual(stats.snapshot.inference_seconds, .012)
        self.assertEqual([call.args[0] for call in record.call_args_list], ["batch_queue", "batch_wait"])

    def test_batch_configuration_updates_between_inputs(self):
        step = YoloDetect(Path("model.pt"), batch=True)
        frames = [context(), context()]

        def inputs():
            yield frames[0]
            step.configure(SimpleNamespace(classes=[2], confidence=.7))
            yield frames[1]

        with patch("pipeworks.embedded.yolo_detect.infer", return_value="result") as infer:
            list(step.process(inputs()))
        self.assertEqual(infer.call_args_list[0].args[2:], (None, .25, 0))
        self.assertEqual(infer.call_args_list[1].args[2:], ([2], .7, 0))

    def test_batch_failure_passes_input_and_recovers(self):
        step = YoloDetect(Path("model.pt"), batch=True)
        frames = [context(), context()]
        with patch("pipeworks.embedded.yolo_detect.infer", side_effect=[RuntimeError("failed"), "recovered"]), \
                self.assertLogs("pipeworks.embedded.yolo_detect", level="ERROR"):
            outputs = list(step.process(iter(frames)))
        self.assertEqual(outputs, frames)
        self.assertEqual([item.detections for item in outputs], [None, "recovered"])

    def test_async_batch_timeout_after_rgb_passes_original(self):
        from pipeworks.local_yolo import _nv12_to_rgb
        entered, release, cleaned = Event(), Event(), Event()
        self.releases.append(release)
        frame = context()
        original = frame.frame
        with torch.cuda.stream(frame.cuda_stream):
            expected = _nv12_to_rgb(original)
        frame.cuda_stream.synchronize()
        observed = []
        def infer(path, image, *args, ready_event, **kwargs):
            ready_event.synchronize()
            observed.append(image)
            entered.set()
            release.wait(5)
            self.assertTrue(torch.equal(image, expected))
            return 'late'
        class ObservedYolo(YoloDetect):
            def process(self, inputs):
                try:
                    yield from super().process(inputs)
                finally:
                    cleaned.set()
        with patch('pipeworks.embedded.yolo_detect.infer', side_effect=infer), patch.object(
            torch.Tensor, 'clone', side_effect=AssertionError('input clone')
        ):
            outputs = CudaAsync(ObservedYolo(self.model_path, batch=True), timeout_ms=100).process(iter([frame]))
            self.assertIs(next(outputs), frame)
            self.assertTrue(entered.wait(1))
            self.assertIs(frame.frame, original)
            self.assertEqual(observed[0].shape, (3, 4, 4))
            self.assertNotEqual(observed[0].data_ptr(), original.data_ptr())
            with torch.cuda.stream(frame.cuda_stream):
                frame.frame.fill_(7)
            frame.cuda_stream.synchronize()
            outputs.close()
            release.set()
            self.assertTrue(cleaned.wait(2))
            self.assertFalse(hasattr(frame, 'detections'))

    def test_async_batch_timeout_before_rgb_drops_frame(self):
        entered, release, cleaned = Event(), Event(), Event()
        self.releases.append(release)
        frame = context()
        original = frame.frame
        prepare = YoloDetect._prepare_rgb
        def blocked_prepare(step, item):
            entered.set()
            release.wait(5)
            return prepare(step, item)
        class ObservedYolo(YoloDetect):
            def process(self, inputs):
                try:
                    yield from super().process(inputs)
                finally:
                    cleaned.set()
        with patch.object(YoloDetect, '_prepare_rgb', blocked_prepare), patch(
            'pipeworks.embedded.yolo_detect.infer', return_value='late'
        ):
            wrapper = CudaAsync(ObservedYolo(self.model_path, batch=True), timeout_ms=100)
            self.assertEqual(list(wrapper.process(iter([frame]))), [])
            self.assertTrue(entered.wait(1))
            self.assertIs(frame.frame, original)
            release.set()
            self.assertTrue(cleaned.wait(2))
            self.assertFalse(hasattr(frame, 'detections'))

    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.model_path = Path(self.directory.name) / "model.pt"
        self.step = YoloDetect(self.model_path)
        self.releases = []
        self.threads = []
        self.addCleanup(self.cleanup_workers)

    def cleanup_workers(self):
        for release in self.releases:
            release.set()
        for worker in self.threads:
            worker.join(5)

    def mock_model(self):
        model = Mock()
        model.predict.side_effect = lambda image, **options: [detection_result()]
        return model

    def test_results_keep_order_interval_model_and_options(self):
        frames = [context() for _ in range(7)]
        originals = [item.frame for item in frames]
        self.step.configure(SimpleNamespace(classes=[2], confidence=0.4, gpu_id=0, inference_interval_frame=3))
        model = self.mock_model()
        with patch("ultralytics.YOLO", return_value=model) as load, patch(
            "pipeworks.embedded.yolo_detect.record_inference"
        ) as record:
            outputs = list(self.step.process(iter(frames)))
        load.assert_called_once_with(str(self.model_path))
        self.assertEqual(model.predict.call_count, 3)
        self.assertEqual(record.call_count, 3)
        for index, item in enumerate(outputs):
            self.assertIs(item, frames[index])
            self.assertIs(item.frame, originals[index])
            self.assertEqual(item.detections is not None, index % 3 == 0)
        options = model.predict.call_args.kwargs
        self.assertEqual((options["classes"], options["conf"], options["device"]), ([2], 0.4, 0))
        self.assertEqual(tuple(model.predict.call_args.args[0].shape), (1, 3, 640, 640))

    def test_loading_and_prediction_run_on_calling_thread(self):
        caller, seen = get_ident(), []
        model = self.mock_model()

        def load(path):
            seen.append(get_ident())
            return model

        def predict(image, **options):
            seen.append(get_ident())
            return [detection_result()]

        model.predict.side_effect = predict
        with patch("ultralytics.YOLO", side_effect=load):
            list(self.step.process(iter([context()])))
        self.assertEqual(seen, [caller, caller])

    def test_initialization_and_inference_wait_until_released(self):
        for block_load in (False, True):
            with self.subTest(block_load=block_load):
                entered, release, returned = Event(), Event(), Event()
                self.releases.append(release)
                model, frame = self.mock_model(), context()
                outputs, errors = [], []

                def block():
                    entered.set()
                    release.wait(5)

                def load(path):
                    if block_load:
                        block()
                    return model

                def predict(image, **options):
                    if not block_load:
                        block()
                    return [detection_result()]

                def consume():
                    try:
                        outputs.extend(self.step.process(iter([frame])))
                    except Exception as error:
                        errors.append(error)
                    finally:
                        returned.set()

                model.predict.side_effect = predict
                with patch("ultralytics.YOLO", side_effect=load):
                    worker = Thread(target=consume)
                    self.threads.append(worker)
                    worker.start()
                    self.assertTrue(entered.wait(2))
                    self.assertFalse(returned.wait(0.05))
                    release.set()
                    worker.join(3)
                self.assertFalse(worker.is_alive())
                self.assertEqual(errors, [])
                self.assertIs(outputs[0], frame)
                self.assertIsNotNone(frame.detections)

    def test_model_sidecar_timeout_is_not_read(self):
        for settings in ("timeout: 0", "timeout: [", "timeout: -1"):
            with self.subTest(settings=settings):
                self.model_path.with_suffix(".yml").write_text(settings, encoding="utf-8")
                frame = context()
                with patch("ultralytics.YOLO", return_value=self.mock_model()):
                    list(self.step.process(iter([frame])))
                self.assertIsNotNone(frame.detections)

    def test_load_and_prediction_errors_propagate(self):
        for fail_load in (False, True):
            with self.subTest(fail_load=fail_load):
                model, error = self.mock_model(), RuntimeError("모델 처리 실패")
                if not fail_load:
                    model.predict.side_effect = error
                with patch("ultralytics.YOLO", side_effect=error if fail_load else None, return_value=model), patch(
                    "pipeworks.embedded.yolo_detect.record_inference"
                ) as record, self.assertRaises(RuntimeError) as caught:
                    list(self.step.process(iter([context()])))
                self.assertIs(caught.exception, error)
                self.assertEqual(record.call_count, 0 if fail_load else 1)

    def test_invalid_inputs_propagate_without_loading_model(self):
        for invalid in ("format", "cpu", "dtype", "shape", "device", "odd", "zero"):
            with self.subTest(invalid=invalid):
                step, item = YoloDetect(self.model_path), context()
                if invalid == "format":
                    item.pixel_format = "P016"
                elif invalid == "cpu":
                    item.frame = torch.zeros((6, 4), dtype=torch.uint8)
                elif invalid == "dtype":
                    item.frame = item.frame.float()
                elif invalid == "shape":
                    item.frame = item.frame[:2]
                elif invalid == "device":
                    step.gpu_id = 1
                elif invalid == "odd":
                    item.video_stream.codec_context.width = 3
                else:
                    item.video_stream.codec_context.height = 0
                with patch("ultralytics.YOLO") as load, patch(
                    "pipeworks.embedded.yolo_detect.record_inference"
                ) as record, self.assertRaises(ValueError):
                    list(step.process(iter([item])))
                load.assert_not_called()
                record.assert_not_called()

    def test_gpu_coordinates_and_separate_stream_without_cpu_copy(self):
        item = context(height=4, width=8)
        result = detection_result(torch.tensor([[80., 160., 560., 480., 0.8, 2]], device="cuda"))
        model, streams = self.mock_model(), []

        def predict(image, **options):
            streams.append(torch.cuda.current_stream(image.device))
            return [result]

        model.predict.side_effect = predict
        with patch("ultralytics.YOLO", return_value=model), patch.object(
            torch.Tensor, "cpu", side_effect=AssertionError("CPU 복사 금지")
        ), patch.object(torch.Tensor, "numpy", side_effect=AssertionError("NumPy 변환 금지")):
            list(self.step.process(iter([item])))
        self.assertNotEqual(streams[0].cuda_stream, item.cuda_stream.cuda_stream)
        self.assertIs(item.detections, result)
        self.assertEqual(result.orig_shape, (4, 8))
        self.assertEqual(result.boxes.orig_shape, (4, 8))
        self.assertEqual(tuple(result.orig_img.shape), (4, 8, 3))
        self.assertTrue(result.orig_img.is_cuda)
        self.assertTrue(result.boxes.data.is_cuda)
        torch.testing.assert_close(result.boxes.xyxy, torch.tensor([[1., 0., 7., 4.]], device="cuda"))
        for option in ("save", "show", "save_txt", "save_crop"):
            self.assertIs(model.predict.call_args.kwargs[option], False)

    def test_inference_statistics_use_calling_scope(self):
        with report_scope():
            stats = _stats()
            with patch("ultralytics.YOLO", return_value=self.mock_model()):
                list(self.step.process(iter([context()])))
            self.assertEqual(stats.snapshot.completed_inferences, 1)
            self.assertGreater(stats.snapshot.inference_seconds, 0)

    def test_async_wrapper_handles_delay_and_discards_late_result(self):
        entered, release, cleaned = Event(), Event(), Event()
        self.releases.append(release)
        model, item = self.mock_model(), context()

        def predict(image, **options):
            entered.set()
            release.wait(5)
            return [detection_result()]

        class ObservedYolo(YoloDetect):
            def process(self, inputs):
                try:
                    yield from super().process(inputs)
                finally:
                    cleaned.set()

        model.predict.side_effect = predict
        with patch("ultralytics.YOLO", return_value=model), report_scope():
            stats = _stats()
            outputs = CudaAsync(ObservedYolo(self.model_path), timeout_ms=10).process(iter([item, context()]))
            self.assertIs(next(outputs), item)
            self.assertTrue(entered.wait(2))
            self.assertFalse(release.is_set())
            self.assertFalse(hasattr(item, "detections"))
            second = next(outputs)
            self.assertFalse(hasattr(second, "detections"))
            outputs.close()
            release.set()
            self.assertTrue(cleaned.wait(3))
            self.assertFalse(hasattr(item, "detections"))
            self.assertEqual(model.predict.call_count, 1)
            self.assertEqual(stats.snapshot.completed_inferences, 1)

    def test_async_wrapper_handles_prediction_failure(self):
        item, model = context(), self.mock_model()
        model.predict.side_effect = RuntimeError("추론 실패")
        with patch("ultralytics.YOLO", return_value=model), self.assertLogs("pipeworks.embedded.cuda_async", level="ERROR"):
            output = list(CudaAsync(self.step, timeout_ms=1000).process(iter([item])))[0]
        self.assertIs(output, item)
        self.assertFalse(hasattr(item, "detections"))

    def _check_real_model(self, suffix):
        model_path = Path(__file__).resolve().parents[1] / "examples" / "model" / f"yolo11n.{suffix}"
        if not model_path.is_file():
            self.skipTest(f"실제 모델 파일이 필요합니다: {model_path}")
        item = context()
        with patch.object(torch.Tensor, "cpu", side_effect=AssertionError("CPU 복사 금지")), patch.object(
            torch.Tensor, "numpy", side_effect=AssertionError("NumPy 변환 금지")
        ):
            list(YoloDetect(model_path).process(iter([item])))
        self.assertEqual(item.detections.orig_shape, (4, 4))
        self.assertTrue(item.detections.orig_img.is_cuda)
        self.assertTrue(item.detections.boxes.data.is_cuda)

    def test_real_pt_model_infers_one_frame(self):
        self._check_real_model("pt")

    def test_real_engine_model_infers_one_frame(self):
        self._check_real_model("engine")


class YoloIntervalConfigurationTests(unittest.TestCase):
    def test_legacy_interval_is_rejected_in_both_modes(self):
        for batch in (False, True):
            for config in ({"inference_interval": 3}, {"inference_interval": 3, "inference_interval_frame": 3}):
                with self.subTest(batch=batch, config=config):
                    step = YoloDetect(Path("model.pt"), batch=batch)
                    with self.assertRaisesRegex(ValueError, "inference_interval_frame"):
                        step.configure(SimpleNamespace(**config))
