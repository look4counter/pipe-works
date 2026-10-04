from pathlib import Path
import runpy
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import torch
import yaml

from pipeworks.embedded import YoloDetect
from pipeworks.models import PipelineContext


def context() -> PipelineContext:
    frame = torch.full((6, 4), 128, dtype=torch.uint8, device="cuda")
    return PipelineContext(
        frame=frame,
        pixel_format=SimpleNamespace(name="NV12"),
        cuda_stream=torch.cuda.Stream(),
        video_stream=SimpleNamespace(codec_context=SimpleNamespace(width=4, height=4)),
    )


class YoloDetectTests(unittest.TestCase):
    def setUp(self):
        timing = patch("pipeworks.embedded.yolo_detect.record_inference")
        self.record_time = timing.start()
        self.addCleanup(timing.stop)

    def test_each_frame_is_inferred_synchronously_with_one_model(self):
        first, second = context(), context()
        result = Mock()
        result.cpu.return_value = result
        model = Mock()
        model.predict.return_value = [result]
        step = YoloDetect(Path("model.engine"))
        step.configure(SimpleNamespace(classes=[2], confidence=0.4, gpu_id=0))

        with patch("ultralytics.YOLO", return_value=model) as load:
            outputs = list(step.process(iter((first, second))))

        self.assertEqual(outputs, [first, second])
        self.assertIs(outputs[0], first)
        self.assertIs(outputs[1], second)
        self.assertIs(first.detections, result)
        self.assertIs(second.detections, result)
        load.assert_called_once_with("model.engine")
        self.assertEqual(model.predict.call_count, 2)
        self.assertEqual(model.predict.call_args.kwargs["classes"], [2])
        self.assertEqual(model.predict.call_args.kwargs["conf"], 0.4)
        self.assertEqual(model.predict.call_args.kwargs["device"], 0)
        self.assertEqual(model.predict.call_args.args[0].shape, (4, 4, 3))
        self.assertEqual(self.record_time.call_count, 2)

    def test_inference_interval_keeps_all_frames_and_clears_skipped_detections(self):
        frames = [context() for _ in range(7)]
        for frame in frames:
            frame.detections = object()
        result = Mock()
        result.cpu.return_value = result
        model = Mock()
        model.predict.return_value = [result]
        step = YoloDetect(Path("model.pt"))
        step.configure(SimpleNamespace(inference_interval=3))

        with patch("ultralytics.YOLO", return_value=model):
            outputs = list(step.process(iter(frames)))

        self.assertEqual(outputs, frames)
        self.assertEqual(model.predict.call_count, 3)
        self.assertEqual(self.record_time.call_count, 3)
        for index, frame in enumerate(frames):
            self.assertIs(frame.detections, result if index % 3 == 0 else None)

    def test_failed_selected_frame_does_not_shift_interval(self):
        frames = [context() for _ in range(5)]
        frames[0].pixel_format = "P016"
        result = Mock()
        result.cpu.return_value = result
        model = Mock()
        model.predict.return_value = [result]
        step = YoloDetect(Path("model.pt"))
        step.configure(SimpleNamespace(inference_interval=3))

        with patch("ultralytics.YOLO", return_value=model), self.assertLogs(
            "pipeworks.embedded.yolo_detect", level="ERROR"
        ):
            outputs = list(step.process(iter(frames)))

        self.assertEqual(outputs, frames)
        self.assertEqual(model.predict.call_count, 1)
        self.assertIs(frames[3].detections, result)
        self.assertTrue(all(frames[index].detections is None for index in (0, 1, 2, 4)))
        self.assertEqual(self.record_time.call_count, 1)

    def test_error_passes_original_frame_and_next_frame_recovers(self):
        first, second = context(), context()
        result = Mock()
        result.cpu.return_value = result
        model = Mock()
        model.predict.side_effect = [RuntimeError("failed"), [result]]
        step = YoloDetect(Path("model.pt"))
        step.configure(SimpleNamespace())

        with patch("ultralytics.YOLO", return_value=model), self.assertLogs(
            "pipeworks.embedded.yolo_detect", level="ERROR"
        ):
            outputs = list(step.process(iter((first, second))))

        self.assertEqual(outputs, [first, second])
        self.assertIsNone(first.detections)
        self.assertIs(second.detections, result)
        self.assertEqual(model.predict.call_count, 2)
        self.assertEqual(self.record_time.call_count, 1)

    def test_each_inference_request_records_one_duration(self):
        first, second = context(), context()
        first.processing_started_at = 10.0
        second.processing_started_at = 10.1
        model = Mock()
        result = Mock()
        result.cpu.return_value = result
        model.predict.return_value = [result]
        with patch("ultralytics.YOLO", return_value=model):
            list(YoloDetect(Path("model.pt")).process(iter((first, second))))
        self.assertEqual(len(self.record_time.call_args_list[0].args), 1)
        self.assertEqual(len(self.record_time.call_args_list[1].args), 1)

    def test_invalid_input_does_not_stop_following_frame(self):
        first, second = context(), context()
        first.pixel_format = "P016"
        result = Mock()
        result.cpu.return_value = result
        model = Mock()
        model.predict.return_value = [result]
        step = YoloDetect(Path("model.pt"))

        with patch("ultralytics.YOLO", return_value=model), self.assertLogs(
            "pipeworks.embedded.yolo_detect", level="ERROR"
        ):
            outputs = list(step.process(iter((first, second))))

        self.assertEqual(outputs, [first, second])
        self.assertIsNone(first.detections)
        self.assertIs(second.detections, result)
        model.predict.assert_called_once()
        self.assertEqual(self.record_time.call_count, 1)

    def test_rejects_invalid_configuration(self):
        for config in (
            SimpleNamespace(classes=[-1]),
            SimpleNamespace(confidence=0),
            SimpleNamespace(gpu_id=-1),
            *(SimpleNamespace(inference_interval=value) for value in (0, -1, True, 1.5, "3", None)),
        ):
            with self.subTest(config=config), self.assertRaises(ValueError):
                YoloDetect(Path("model.pt")).configure(config)

    def test_default_inference_interval_is_one(self):
        step = YoloDetect(Path("model.pt"))
        step.configure(SimpleNamespace())
        self.assertEqual(step.inference_interval, 1)

    def test_stream_config_applies_to_single_detector(self):
        config_path = Path(__file__).resolve().parents[1] / "examples" / "config" / "stream.yml"
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))["YoloDetect"]
        detector = YoloDetect(Path("model.pt"))
        detector.configure(SimpleNamespace(**config))
        self.assertEqual(detector.inference_interval, config["inference_interval"])
        self.assertEqual(detector.classes, config["classes"])
        self.assertEqual(detector.confidence, config["confidence"])
        self.assertEqual(detector.gpu_id, config["gpu_id"])

        result = Mock()
        result.cpu.return_value = result
        model = Mock()
        model.predict.return_value = [result]
        with patch("ultralytics.YOLO", return_value=model):
            list(detector.process(iter((context(),))))
        self.assertEqual(model.predict.call_args.kwargs["classes"], config["classes"])
        self.assertEqual(model.predict.call_args.kwargs["conf"], config["confidence"])
        self.assertEqual(model.predict.call_args.kwargs["device"], config["gpu_id"])

    def test_real_pt_and_engine_models_infer_one_frame(self):
        model_dir = Path(__file__).resolve().parents[1] / "examples" / "model"
        for suffix in ("pt", "engine"):
            with self.subTest(suffix=suffix):
                step = YoloDetect(model_dir / f"yolo11n.{suffix}")
                step.configure(SimpleNamespace(classes=[2], gpu_id=0))
                item = context()
                outputs = list(step.process(iter((item,))))
                self.assertEqual(outputs, [item])
                self.assertEqual(item.detections.orig_shape, (4, 4))
                self.assertEqual(item.detections.boxes.data.device.type, "cpu")
        self.assertEqual(self.record_time.call_count, 2)


if __name__ == "__main__":
    unittest.main()
