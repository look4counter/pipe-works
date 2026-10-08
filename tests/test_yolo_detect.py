from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from threading import Event
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import torch
from ultralytics.engine.results import Results

from pipeworks.embedded import YoloDetect
from pipeworks.embedded.stream_report import _stats, report_scope
from pipeworks.models import PipelineContext


def context(height=4, width=4):
    stream = torch.cuda.Stream()
    with torch.cuda.stream(stream):
        frame = torch.full((height * 3 // 2, width), 128, dtype=torch.uint8, device="cuda")
    return PipelineContext(
        frame=frame, pixel_format="NV12", cuda_stream=stream,
        video_stream=SimpleNamespace(codec_context=SimpleNamespace(width=width, height=height)),
    )


def detection_result(boxes=None):
    if boxes is None:
        boxes = torch.empty((0, 6), device="cuda")
    return Results(torch.zeros((640, 640, 3), device="cuda"), path="image", names={2: "car"}, boxes=boxes)


class YoloTimeoutTests(unittest.TestCase):
    def test_model_sidecar_timeout_defaults_and_units(self):
        with TemporaryDirectory() as directory:
            for suffix in ("pt", "engine"):
                model = Path(directory) / f"model.{suffix}"
                settings = model.with_suffix(".yml")
                if settings.exists():
                    settings.unlink()
                step = YoloDetect(model)
                self.assertEqual(step._timeout_seconds(), 0.005)
                for content, expected in (
                    ("max_batch_size: 10\ntimeout: 25", 0.025),
                    ("timeout: 0", 0.0), ("timeout: 1.5", 0.0015), ("{}", 0.005),
                ):
                    settings.write_text(content, encoding="utf-8")
                    self.assertEqual(step._timeout_seconds(), expected)

    def test_invalid_sidecar_timeout_is_rejected(self):
        with TemporaryDirectory() as directory:
            model = Path(directory) / "model.pt"
            for content in ("timeout: true", "timeout: -1", "timeout: .inf", "timeout: .nan",
                            "timeout: null", 'timeout: "5"', "[]", "timeout: ["):
                with self.subTest(content=content):
                    model.with_suffix(".yml").write_text(content, encoding="utf-8")
                    with self.assertRaises(ValueError):
                        YoloDetect(model)._timeout_seconds()

    def test_configuration_is_preserved_and_invalid_values_rejected(self):
        step = YoloDetect(Path("model.pt"))
        step.configure(SimpleNamespace(classes=[2], confidence=0.4, gpu_id=0, inference_interval=3))
        self.assertEqual((step.classes, step.confidence, step.gpu_id, step.inference_interval), ([2], 0.4, 0, 3))
        self.assertEqual(YoloDetect(Path("model.pt")).inference_interval, 1)
        for config in (SimpleNamespace(classes=[-1]), SimpleNamespace(confidence=0), SimpleNamespace(gpu_id=-1),
                       *(SimpleNamespace(inference_interval=value) for value in (0, -1, True, 1.5, "3", None))):
            with self.subTest(config=config), self.assertRaises(ValueError):
                YoloDetect(Path("model.pt")).configure(config)


@unittest.skipUnless(torch.cuda.is_available(), "CUDA가 필요합니다.")
class YoloDetectTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.model_path = Path(self.directory.name) / "model.pt"
        self.model_path.with_suffix(".yml").write_text("timeout: 2000", encoding="utf-8")
        self.step = YoloDetect(self.model_path)
        self.steps = [self.step]
        self.releases = []
        self.addCleanup(self.stop_workers)
        timing = patch("pipeworks.embedded.yolo_detect.record_inference")
        self.record_time = timing.start()
        self.addCleanup(timing.stop)

    def stop_workers(self):
        for release in self.releases:
            release.set()
        for step in self.steps:
            worker = getattr(step, "_worker", None)
            if worker is not None:
                worker.close()
                worker.thread.join(timeout=5)

    def mock_model(self):
        model = Mock()
        model.predict.side_effect = lambda image, **options: [detection_result()]
        return model

    def block_model(self):
        entered, release = Event(), Event()
        self.releases.append(release)
        model = self.mock_model()

        def predict(image, **options):
            entered.set()
            release.wait(5)
            return [detection_result()]

        model.predict.side_effect = predict
        return model, entered, release

    def test_completed_results_keep_order_interval_model_and_options(self):
        frames = [context() for _ in range(7)]
        for frame in frames:
            frame.detections = object()
        self.step.configure(SimpleNamespace(classes=[2], confidence=0.4, gpu_id=0, inference_interval=3))
        model = self.mock_model()
        with patch("ultralytics.YOLO", return_value=model) as load:
            outputs = list(self.step.process(iter(frames)))
        self.assertEqual(outputs, frames)
        load.assert_called_once_with(str(self.model_path))
        self.assertEqual(model.predict.call_count, 3)
        self.assertEqual(self.record_time.call_count, 3)
        for index, frame in enumerate(frames):
            if index % 3 == 0:
                self.assertIsNotNone(frame.detections)
                self.assertTrue(frame.detections.boxes.data.is_cuda)
            else:
                self.assertIsNone(frame.detections)
        options = model.predict.call_args.kwargs
        self.assertEqual((options["classes"], options["conf"], options["device"]), ([2], 0.4, 0))
        self.assertEqual(tuple(model.predict.call_args.args[0].shape), (1, 3, 640, 640))

    def test_stalled_inference_passes_all_frames_and_close_does_not_wait(self):
        self.model_path.with_suffix(".yml").write_text("timeout: 5", encoding="utf-8")
        frames = [context() for _ in range(30)]
        model, entered, release = self.block_model()
        with patch("ultralytics.YOLO", return_value=model), patch.object(
            self.step, "_copy_frame", wraps=self.step._copy_frame
        ) as copy:
            outputs = self.step.process(iter(frames))
            started = time.monotonic()
            first = next(outputs)
            self.assertLess(time.monotonic() - started, 0.2)
            self.assertTrue(entered.wait(2))
            self.assertFalse(release.is_set())
            worker = self.step._worker
            self.assertEqual([first, *outputs], frames)
            self.assertEqual(copy.call_count, 1)
            self.assertEqual(model.predict.call_count, 1)
            self.assertTrue(all(frame.detections is None for frame in frames))
            self.assertTrue(worker.thread.is_alive())
            self.assertEqual(worker.requests.qsize(), 0)
            repeated = context()
            self.assertEqual(list(self.step.process(iter((repeated,)))), [repeated])
            self.assertIs(self.step._worker, worker)
            release.set()
            worker.thread.join(3)
            self.assertFalse(worker.thread.is_alive())
            self.assertTrue(all(frame.detections is None for frame in frames))

    def test_first_model_loading_is_also_bounded(self):
        self.model_path.with_suffix(".yml").write_text("timeout: 5", encoding="utf-8")
        entered, release = Event(), Event()
        self.releases.append(release)

        def load(path):
            entered.set()
            release.wait(5)
            return self.mock_model()

        with patch("ultralytics.YOLO", side_effect=load):
            outputs = self.step.process(iter((context(), context())))
            first = next(outputs)
            self.assertIsNone(first.detections)
            self.assertTrue(entered.wait(2))
            started = time.monotonic()
            second = next(outputs)
            outputs.close()
            self.assertLess(time.monotonic() - started, 0.2)
            self.assertIsNone(second.detections)
            self.assertTrue(self.step._worker.thread.is_alive())
            release.set()
            self.step._worker.thread.join(3)

    def test_late_result_is_discarded_and_later_inference_recovers(self):
        self.model_path.with_suffix(".yml").write_text("timeout: 5", encoding="utf-8")
        model, entered, release = self.block_model()
        frames = [context(), context()]
        with patch("ultralytics.YOLO", return_value=model):
            outputs = self.step.process(iter(frames))
            first = next(outputs)
            self.assertTrue(entered.wait(2))
            request = self.step._worker.current
            release.set()
            self.assertTrue(request.done.wait(3))
            self.assertIsNone(first.detections)
            self.assertIsNone(request.result)
            second = next(outputs)
            outputs.close()
            self.assertIsNone(first.detections)
            self.assertEqual(model.predict.call_count, 2)
            self.assertIs(second, frames[1])

    def test_inference_and_model_load_failure_recover(self):
        for fail_load in (False, True):
            with self.subTest(fail_load=fail_load):
                recorded_before = self.record_time.call_count
                step = YoloDetect(self.model_path)
                self.steps.append(step)
                frames = [context(), context()]
                model = self.mock_model()
                if not fail_load:
                    model.predict.side_effect = [RuntimeError("추론 실패"), [detection_result()]]
                load_values = [RuntimeError("모델 초기화 실패"), model] if fail_load else None
                with patch("ultralytics.YOLO", side_effect=load_values, return_value=model), self.assertLogs(
                    "pipeworks.embedded.yolo_detect", level="ERROR"
                ):
                    outputs = list(step.process(iter(frames)))
                self.assertEqual(outputs, frames)
                self.assertIsNone(frames[0].detections)
                self.assertIsNotNone(frames[1].detections)
                self.assertEqual(self.record_time.call_count - recorded_before, 1 if fail_load else 2)

    def test_gpu_copy_free_coordinates_and_separate_inference_stream(self):
        item = context(height=4, width=8)
        result = detection_result(torch.tensor([[80., 160., 560., 480., 0.8, 2]], device="cuda"))
        model = self.mock_model()
        streams = []

        def predict(image, **options):
            streams.append(torch.cuda.current_stream(image.device))
            return [result]

        model.predict.side_effect = predict
        with patch("ultralytics.YOLO", return_value=model), patch.object(
            torch.Tensor, "cpu", side_effect=AssertionError("CPU 복사 금지")
        ), patch.object(torch.Tensor, "numpy", side_effect=AssertionError("NumPy 변환 금지")):
            outputs = list(self.step.process(iter((item,))))
        self.assertEqual(outputs, [item])
        self.assertIs(item.detections, result)
        self.assertNotEqual(streams[0].cuda_stream, item.cuda_stream.cuda_stream)
        self.assertEqual(tuple(result.orig_shape), (4, 8))
        self.assertEqual(tuple(result.boxes.orig_shape), (4, 8))
        self.assertEqual(tuple(result.orig_img.shape), (4, 8, 3))
        self.assertTrue(result.orig_img.is_cuda)
        self.assertTrue(result.boxes.data.is_cuda)
        torch.testing.assert_close(result.boxes.xyxy, torch.tensor([[1., 0., 7., 4.]], device="cuda"))
        for option in ("save", "show", "save_txt", "save_crop"):
            self.assertIs(model.predict.call_args.kwargs[option], False)

    def test_invalid_inputs_and_failed_interval_do_not_stop_video(self):
        for invalid in ("format", "cpu", "dtype", "shape", "device", "odd"):
            with self.subTest(invalid=invalid):
                step = YoloDetect(self.model_path)
                self.steps.append(step)
                frames = [context() for _ in range(5)]
                first = frames[0]
                if invalid == "format":
                    first.pixel_format = "P016"
                elif invalid == "cpu":
                    first.frame = torch.zeros((6, 4), dtype=torch.uint8)
                elif invalid == "dtype":
                    first.frame = first.frame.float()
                elif invalid == "shape":
                    first.frame = first.frame[:2]
                elif invalid == "odd":
                    first.video_stream.codec_context.width = 3
                step.inference_interval = 3
                if invalid == "device":
                    step.gpu_id = 1
                model = self.mock_model()
                with patch("ultralytics.YOLO", return_value=model), self.assertLogs(
                    "pipeworks.embedded.yolo_detect", level="ERROR"
                ):
                    outputs = list(step.process(iter(frames)))
                self.assertEqual(outputs, frames)
                self.assertIsNone(first.detections)
                if invalid != "device":
                    self.assertIsNotNone(frames[3].detections)
                    self.assertEqual(model.predict.call_count, 1)
                else:
                    model.predict.assert_not_called()

    def test_zero_timeout_never_waits_for_blocked_worker(self):
        self.model_path.with_suffix(".yml").write_text("timeout: 0", encoding="utf-8")
        model, entered, release = self.block_model()
        with patch("ultralytics.YOLO", return_value=model):
            item = context()
            outputs = self.step.process(iter((item,)))
            self.assertIs(next(outputs), item)
            self.assertIsNone(item.detections)
            self.assertTrue(entered.wait(2))
            outputs.close()
            release.set()
            self.step._worker.thread.join(3)

    def test_worker_statistics_belong_to_submission_scope_even_after_timeout(self):
        self.model_path.with_suffix(".yml").write_text("timeout: 5", encoding="utf-8")
        model, entered, release = self.block_model()
        from pipeworks.embedded.stream_report import record_inference
        with patch("pipeworks.embedded.yolo_detect.record_inference", record_inference), patch(
            "ultralytics.YOLO", return_value=model
        ):
            with report_scope():
                submitted_stats = _stats()
                outputs = self.step.process(iter((context(),)))
                next(outputs)
                self.assertTrue(entered.wait(2))
                request = self.step._worker.current
                outputs.close()
            with report_scope():
                other_stats = _stats()
                release.set()
                self.assertTrue(request.done.wait(3))
                self.assertEqual(submitted_stats.completed_inferences, 1)
                self.assertEqual(other_stats.completed_inferences, 0)
                self.assertIsNone(request.image)
                self.assertIsNone(request.source_owner)

    def _check_real_model(self, suffix):
        model_dir = Path(__file__).resolve().parents[1] / "examples" / "model"
        model_path = model_dir / f"yolo11n.{suffix}"
        if not model_path.is_file():
            self.skipTest(f"실제 모델 파일이 필요합니다: {model_path}")
        local_model = Path(self.directory.name) / f"model.{suffix}"
        shutil.copyfile(model_path, local_model)
        local_model.with_suffix(".yml").write_text("timeout: 10000", encoding="utf-8")
        step = YoloDetect(local_model)
        self.steps.append(step)
        item = context()
        with patch.object(torch.Tensor, "cpu", side_effect=AssertionError("CPU 복사 금지")), patch.object(
            torch.Tensor, "numpy", side_effect=AssertionError("NumPy 변환 금지")
        ):
            outputs = list(step.process(iter((item,))))
        self.assertEqual(outputs, [item])
        self.assertIsNotNone(item.detections)
        self.assertEqual(item.detections.orig_shape, (4, 4))
        self.assertTrue(item.detections.orig_img.is_cuda)
        self.assertTrue(item.detections.boxes.data.is_cuda)

    def test_real_pt_model_infers_one_frame(self):
        self._check_real_model("pt")

    def test_real_engine_model_infers_one_frame(self):
        self._check_real_model("engine")


if __name__ == "__main__":
    unittest.main()
