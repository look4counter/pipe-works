from pathlib import Path
import runpy
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import torch

from pipeworks.embedded import CudaAsync, NvidiaEncode, TensorRTInference
from pipeworks.models import PipelineContext


class BoxOverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        example = Path(__file__).resolve().parents[1] / "examples" / "01_single_stream_rtsp_style.py"
        with patch.object(sys, "path", [str(example.parent), *sys.path]):
            cls.example = runpy.run_path(str(example))

    def test_example_places_configured_overlay_before_encoder(self):
        pipeline = self.example["build_pipeline"]()
        steps = []
        for registered in pipeline.steps:
            step = getattr(registered, "wrapped_step", registered)
            steps.extend(step.steps if isinstance(step, CudaAsync) else [step])
        overlay = next(step for step in steps if isinstance(step, self.example["BoxOverlay"]))
        detect = next(step for step in steps if isinstance(step, TensorRTInference))
        self.assertLess(steps.index(detect), steps.index(overlay))
        self.assertLess(steps.index(overlay), steps.index(next(step for step in steps if isinstance(step, NvidiaEncode))))
        config = pipeline.config.BoxOverlay
        self.assertEqual((overlay.line_width, overlay.line_color, overlay.keep_previous), (config["line_width"], config["line_color"], config["keep_previous"]))

    def test_rejects_invalid_overlay_options(self):
        for settings in (
            {"line_width": 0}, {"line_width": True}, {"line_width": 1.5},
            {"line_color": "green"}, {"line_color": "#00ff0"},
            {"keep_previous": 1},
        ):
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                self.example["BoxOverlay"]().configure(SimpleNamespace(**settings))

    def test_rejects_unsupported_pixel_format(self):
        overlay = self.example["BoxOverlay"]()
        overlay.configure(SimpleNamespace())
        item = PipelineContext(
            pixel_format="P016", video_stream=SimpleNamespace(codec_context=SimpleNamespace(width=8, height=8)),
            detections=None,
        )
        with self.assertRaisesRegex(ValueError, "NV12"):
            list(overlay.process(iter((item,))))

    @unittest.skipUnless(torch.cuda.is_available(), "CUDA가 필요합니다.")
    def test_draws_nv12_rectangle_on_original_gpu_frame_and_reuses_previous_boxes(self):
        overlay = self.example["BoxOverlay"]()
        overlay.configure(SimpleNamespace(line_width=2, line_color="#00ff00", keep_previous=True))
        stream = torch.cuda.Stream()

        def item(boxes):
            with torch.cuda.stream(stream):
                frame = torch.full((12, 8), 16, dtype=torch.uint8, device="cuda")
                frame[8:, :] = 128
                tensor = None if boxes is None else torch.tensor(boxes, dtype=torch.float32, device="cuda").reshape(-1, 4)
            detections = None if tensor is None else SimpleNamespace(boxes=SimpleNamespace(xyxy=tensor))
            return PipelineContext(
                frame=frame, detections=detections, cuda_stream=stream,
                pixel_format="NV12", video_stream=SimpleNamespace(codec_context=SimpleNamespace(width=8, height=8)),
            )

        first = item([[1, 1, 6, 6]])
        original_frame_pointer = first.frame.data_ptr()
        reused = item(None)
        empty = item([])
        cleared = item(None)
        detections = first.detections
        with patch.object(torch.Tensor, "cpu", side_effect=AssertionError("CPU copy")), patch.object(torch.Tensor, "tolist", side_effect=AssertionError("CPU list")), patch.object(torch.Tensor, "item", side_effect=AssertionError("scalar read")):
            outputs = list(overlay.process(iter((first, reused, empty, cleared))))
        self.assertIs(first.detections, detections)
        stream.synchronize()

        self.assertEqual(outputs, [first, reused, empty, cleared])
        self.assertEqual(first.frame.data_ptr(), original_frame_pointer)
        for context in (first, reused):
            self.assertTrue(context.frame.is_cuda)
            self.assertEqual(context.frame[1, 1].item(), 145)
            self.assertEqual(context.frame[2, 5].item(), 145)
            self.assertEqual(context.frame[3, 3].item(), 16)
            self.assertEqual(context.frame[8, 0].item(), 54)
            self.assertEqual(context.frame[8, 1].item(), 34)
        self.assertEqual(empty.frame[:8].max().item(), 16)
        self.assertEqual(cleared.frame[:8].max().item(), 16)

    @unittest.skipUnless(torch.cuda.is_available(), "CUDA가 필요합니다.")
    def test_clips_boxes_and_does_not_reuse_when_disabled(self):
        overlay = self.example["BoxOverlay"]()
        overlay.configure(SimpleNamespace(line_width=1, line_color="#ff0000", keep_previous=False))
        stream = torch.cuda.Stream()
        with torch.cuda.stream(stream):
            frame = torch.full((12, 8), 16, dtype=torch.uint8, device="cuda")
            frame[8:] = 128
            boxes = torch.tensor([[-3, -2, 3, 3], [10, 10, 12, 12]], dtype=torch.float32, device="cuda")
            second_frame = frame.clone()
        metadata = dict(cuda_stream=stream, pixel_format="NV12", video_stream=SimpleNamespace(codec_context=SimpleNamespace(width=8, height=8)))
        first = PipelineContext(frame=frame, detections=SimpleNamespace(boxes=SimpleNamespace(xyxy=boxes)), **metadata)
        second = PipelineContext(frame=second_frame, detections=None, **metadata)
        self.assertEqual(list(overlay.process(iter((first, second)))), [first, second])
        stream.synchronize()
        self.assertNotEqual(first.frame[0, 0].item(), 16)
        self.assertEqual(second.frame[:8].max().item(), 16)
