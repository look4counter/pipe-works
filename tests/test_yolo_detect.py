from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread, get_ident
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import torch
from ultralytics.engine.results import Results

from pipeworks.embedded import Async, YoloDetect
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
    def test_configuration_and_validation(self):
        step = YoloDetect(Path("model.pt"))
        step.configure(SimpleNamespace(classes=[2], confidence=0.4, gpu_id=0, inference_interval=3))
        self.assertEqual((step.classes, step.confidence, step.gpu_id, step.inference_interval), ([2], 0.4, 0, 3))
        self.assertEqual(YoloDetect(Path("model.pt")).inference_interval, 1)
        for config in (SimpleNamespace(classes=[True]), SimpleNamespace(classes=[-1]),
                       SimpleNamespace(confidence=0), SimpleNamespace(gpu_id=-1),
                       *(SimpleNamespace(inference_interval=value) for value in (0, -1, True, 1.5, "3", None))):
            with self.subTest(config=config), self.assertRaises(ValueError):
                step.configure(config)

    def test_internal_async_and_timeout_are_removed(self):
        step = YoloDetect(Path("model.pt"))
        self.assertFalse(hasattr(step, "_worker"))
        self.assertFalse(hasattr(step, "_timeout_seconds"))


@unittest.skipUnless(torch.cuda.is_available(), "CUDA가 필요합니다.")
class YoloDetectTests(unittest.TestCase):
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
        self.step.configure(SimpleNamespace(classes=[2], confidence=0.4, gpu_id=0, inference_interval=3))
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
            self.assertEqual(stats.completed_inferences, 1)
            self.assertGreater(stats.inference_seconds, 0)

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
            outputs = Async(ObservedYolo(self.model_path), timeout_ms=10).process(iter([item, context()]))
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
            self.assertEqual(stats.completed_inferences, 1)

    def test_async_wrapper_handles_prediction_failure(self):
        item, model = context(), self.mock_model()
        model.predict.side_effect = RuntimeError("추론 실패")
        with patch("ultralytics.YOLO", return_value=model), self.assertLogs("pipeworks.embedded.async_step", level="ERROR"):
            output = list(Async(self.step, timeout_ms=1000).process(iter([item])))[0]
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
