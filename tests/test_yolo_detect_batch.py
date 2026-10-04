from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory
from threading import Event, Thread
import unittest
from unittest.mock import patch

import torch

from pipeworks.embedded.yolo_detect_batch import YoloDetectBatch
from pipeworks.models import PipelineContext


def context() -> PipelineContext:
    stream = torch.cuda.Stream()
    nv12 = torch.full((6, 4), 128, dtype=torch.uint8, device="cuda")
    nv12[:4] = 80
    return PipelineContext(
        frame=nv12,
        pixel_format=SimpleNamespace(name="NV12"),
        cuda_stream=stream,
        video_stream=SimpleNamespace(codec_context=SimpleNamespace(width=4, height=4)),
    )


class YoloDetectBatchTests(unittest.TestCase):
    def test_process_has_no_input_prefetch(self):
        step = YoloDetectBatch(Path("model.pt"))
        step.configure(SimpleNamespace(inference_interval=3))
        frames = [context() for _ in range(7)]
        pulled = []
        self.infer.side_effect = ["first", "fourth", "seventh"]

        def source():
            for frame in frames:
                pulled.append(frame)
                yield frame

        output = step.process(source())
        self.assertIs(next(output), frames[0])
        self.assertEqual(pulled, frames[:1])
        self.assertEqual([frames[0], *list(output)], frames)
        self.assertEqual([frame.detections for frame in frames],
                         ["first", None, None, "fourth", None, None, "seventh"])
        self.assertEqual(self.infer.call_count, 3)

    def test_slow_inference_does_not_read_next_frame(self):
        step = YoloDetectBatch(Path("model.pt"))
        first, second = context(), context()
        started = Event()
        release = Event()
        pulled = []
        outputs = []

        def source():
            for frame in (first, second):
                pulled.append(frame)
                yield frame

        def slow_infer(*_, **__):
            started.set()
            release.wait(2)
            return "detected"

        self.infer.side_effect = slow_infer
        runner = Thread(target=lambda: outputs.extend(step.process(source())))
        runner.start()
        try:
            self.assertTrue(started.wait(2))
            self.assertEqual(pulled, [first])
        finally:
            release.set()
            runner.join(timeout=5)
        self.assertFalse(runner.is_alive())
        self.assertEqual(outputs, [first, second])

    def test_removed_low_latency_setting_is_rejected(self):
        for value in (True, False):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "low_latency"):
                YoloDetectBatch(Path("model.pt")).configure(SimpleNamespace(low_latency=value))

    def test_failed_frame_passes_through_and_recovers(self):
        step = YoloDetectBatch(Path("model.pt"))
        step.configure(SimpleNamespace())
        frames = [context(), context()]
        self.infer.side_effect = [RuntimeError("failed"), "recovered"]
        with self.assertLogs("pipeworks.embedded.yolo_detect_batch", level="ERROR"):
            self.assertEqual(list(step.process(iter(frames))), frames)
        self.assertEqual([frame.detections for frame in frames], [None, "recovered"])

    def test_selected_frame_does_not_synchronize_host_before_queueing(self):
        step = YoloDetectBatch(Path("model.pt"))
        step.configure(SimpleNamespace())
        item = context()
        with patch.object(torch.cuda.Stream, "synchronize", side_effect=AssertionError("host sync")):
            self.assertEqual(list(step.process(iter((item,)))), [item])
        self.assertIn("ready_event", self.infer.call_args.kwargs)
        self.assertIsInstance(self.infer.call_args.kwargs["ready_event"], torch.cuda.Event)

    def setUp(self):
        inference = patch("pipeworks.embedded.yolo_detect_batch.infer")
        self.infer = inference.start()
        def completed_infer(*args, **kwargs):
            kwargs["on_inference_complete"](0.012)
            return self.infer.return_value
        self.infer.side_effect = completed_infer
        self.addCleanup(inference.stop)
        inference_time = patch("pipeworks.embedded.yolo_detect_batch.record_inference")
        self.record_inference = inference_time.start()
        self.addCleanup(inference_time.stop)

    def test_inference_retries_after_failure(self):
        with TemporaryDirectory() as directory:
            weights = Path(directory) / "model.pt"
            weights.write_bytes(b"test")
            step = YoloDetectBatch(weights)
            step.configure(SimpleNamespace())
            first, second, third = context(), context(), context()
            result = object()
            self.infer.side_effect = [RuntimeError("start failed"), result, result]
            with self.assertLogs("pipeworks.embedded.yolo_detect_batch", level="ERROR"):
                outputs = list(step.process(iter((first, second, third))))

            self.assertEqual(outputs, [first, second, third])
            self.assertIsNone(first.detections)
            self.assertIs(second.detections, result)
            self.assertIs(third.detections, result)
            self.assertEqual(self.infer.call_count, 3)

    def test_engine_path_uses_worker(self):
        with TemporaryDirectory() as directory:
            engine = Path(directory) / "model.engine"
            engine.write_bytes(b"test")
            item = context()
            result = object()
            step = YoloDetectBatch(engine)
            step.configure(SimpleNamespace(classes=[2], gpu_id=0))

            self.infer.return_value = result
            outputs = list(step.process(iter((item,))))

            self.assertEqual(outputs, [item])
            self.assertIs(item.detections, result)
            self.assertEqual(self.infer.call_args.args[0], engine)

    def test_inference_keeps_frame_and_passes_car_filter(self):
        with TemporaryDirectory() as directory:
            weights = Path(directory) / "model.pt"
            weights.write_bytes(b"test")
            step = YoloDetectBatch(weights)
            step.configure(SimpleNamespace(classes=[2], confidence=0.4, gpu_id=1))
            first, second = context(), context()
            result = object()

            self.infer.return_value = result
            outputs = list(step.process(iter((first, second))))

            self.assertEqual(outputs, [first, second])
            self.assertIs(first.detections, result)
            self.assertIs(second.detections, result)
            self.assertEqual(first.frame.shape, (6, 4))
            self.assertEqual(self.infer.call_count, 2)
            image = self.infer.call_args.args[1]
            self.assertEqual(image.dtype, torch.uint8)
            self.assertEqual(image.shape, (6, 4))
            self.assertTrue(image.is_cuda)
            self.assertEqual(self.infer.call_args.args[2:], ([2], 0.4, 1))

    def test_gpu_id_defaults_to_zero(self):
        step = YoloDetectBatch(Path("model.pt"))
        step.configure(SimpleNamespace())
        self.assertEqual(step.gpu_id, 0)
        self.assertEqual(step.inference_interval, 1)

    def test_inference_interval_requests_only_every_third_frame(self):
        step = YoloDetectBatch(Path("model.pt"))
        step.configure(SimpleNamespace(inference_interval=3))
        frames = [context() for _ in range(7)]
        for frame in frames:
            frame.detections = "old"
        self.infer.side_effect = ["first", "fourth", "seventh"]

        outputs = list(step.process(iter(frames)))

        self.assertEqual(outputs, frames)
        self.assertEqual([frame.detections for frame in frames], ["first", None, None, "fourth", None, None, "seventh"])
        self.assertEqual(self.infer.call_count, 3)
        self.assertEqual(self.record_inference.call_count, 0)

    def test_multiple_steps_record_only_inference_time(self):
        first_step = YoloDetectBatch(Path("first.pt"))
        first_step.configure(SimpleNamespace(inference_interval=3))
        first_frames = [context() for _ in range(7)]
        for index, frame in enumerate(first_frames):
            frame.processing_started_at = index / 30
        list(first_step.process(iter(first_frames)))

        second_step = YoloDetectBatch(Path("second.pt"))
        second_step.configure(SimpleNamespace(inference_interval=2))
        second_frames = [context() for _ in range(5)]
        for index, frame in enumerate(second_frames):
            frame.processing_started_at = index / 25
        list(second_step.process(iter(second_frames)))

        self.assertEqual(self.record_inference.call_count, 6)
        self.assertTrue(all(call.args == (0.012,) for call in self.record_inference.call_args_list))

    def test_inference_interval_rejects_invalid_values(self):
        for value in (0, -1, True, 1.5, "3"):
            with self.subTest(value=value):
                step = YoloDetectBatch(Path("model.pt"))
                with self.assertRaisesRegex(ValueError, "inference_interval"):
                    step.configure(SimpleNamespace(inference_interval=value))

    def test_failed_request_does_not_shift_inference_interval(self):
        step = YoloDetectBatch(Path("model.pt"))
        step.configure(SimpleNamespace(inference_interval=3))
        frames = [context() for _ in range(5)]
        self.infer.side_effect = [RuntimeError("inference failed"), "fourth"]

        with self.assertLogs("pipeworks.embedded.yolo_detect_batch", level="ERROR"):
            outputs = list(step.process(iter(frames)))

        self.assertEqual(outputs, frames)
        self.assertEqual([frame.detections for frame in frames], [None, None, None, "fourth", None])
        self.assertEqual(self.infer.call_count, 2)
        self.assertEqual(self.record_inference.call_count, 0)

    def test_missing_model_passes_frames_through(self):
        with TemporaryDirectory() as directory:
            step = YoloDetectBatch(Path(directory) / "missing.pt")
            first, second = context(), context()
            self.infer.side_effect = FileNotFoundError("missing model")
            with self.assertLogs("pipeworks.embedded.yolo_detect_batch", level="ERROR") as logs:
                outputs = list(step.process(iter((first, second))))
            self.assertEqual(outputs, [first, second])
            self.assertIsNone(first.detections)
            self.assertIsNone(second.detections)
            self.assertEqual(len(logs.records), 2)

    def test_unsupported_pixel_format_passes_frame_and_next_frame_runs(self):
        with TemporaryDirectory() as directory:
            weights = Path(directory) / "model.pt"
            weights.write_bytes(b"test")
            first, second = context(), context()
            first.pixel_format = "P016"
            result = object()
            step = YoloDetectBatch(weights)
            step.configure(SimpleNamespace())
            self.infer.return_value = result
            with self.assertLogs("pipeworks.embedded.yolo_detect_batch", level="ERROR"):
                outputs = list(step.process(iter((first, second))))
            self.assertEqual(outputs, [first, second])
            self.assertIsNone(first.detections)
            self.assertIs(second.detections, result)

    def test_prediction_error_passes_frame_and_recovers(self):
        with TemporaryDirectory() as directory:
            weights = Path(directory) / "model.pt"
            weights.write_bytes(b"test")
            first, second = context(), context()
            result = object()
            step = YoloDetectBatch(weights)
            step.configure(SimpleNamespace())
            self.infer.side_effect = [RuntimeError("inference failed"), result]
            with self.assertLogs("pipeworks.embedded.yolo_detect_batch", level="ERROR"):
                outputs = list(step.process(iter((first, second))))
            self.assertEqual(outputs, [first, second])
            self.assertIsNone(first.detections)
            self.assertIs(second.detections, result)
            self.assertEqual(self.infer.call_count, 2)
