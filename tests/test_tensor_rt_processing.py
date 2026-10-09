import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))
from step.tensor_rt_pre_process import TensorRTPreProcess
from step.tensor_rt_post_process import TensorRTPostProcess
from pipeworks.models import PipelineContext


@unittest.skipUnless(torch.cuda.is_available(), "CUDA가 필요합니다.")
class ProcessingTests(unittest.TestCase):
    def frame(self):
        stream = torch.cuda.Stream()
        with torch.cuda.stream(stream):
            frame = torch.full((6, 8), 128, dtype=torch.uint8, device="cuda")
            frame[:4] = 16
        return PipelineContext(frame=frame, pixel_format="NV12", cuda_stream=stream,
                               video_stream=SimpleNamespace(codec_context=SimpleNamespace(height=4, width=8)))

    def test_preprocess_keeps_input_and_padding_on_gpu(self):
        item = self.frame()
        item.cuda_stream.synchronize()
        original = item.frame.clone()
        with patch.object(torch.Tensor, "cpu", side_effect=AssertionError("CPU copy")):
            self.assertIs(next(TensorRTPreProcess().process(iter([item]))), item)
        item.cuda_stream.synchronize()
        self.assertEqual(tuple(item.model_input.shape), (1, 3, 640, 640))
        self.assertTrue(item.model_input.is_cuda)
        self.assertNotEqual(item.model_cuda_stream.cuda_stream, item.cuda_stream.cuda_stream)
        self.assertEqual(item.model_input.dtype, torch.float32)
        self.assertTrue(torch.equal(item.frame, original))
        self.assertAlmostEqual(item.model_input[0, 0, 0, 0].item(), 114 / 255, places=5)
        self.assertEqual(item.model_input[0, 0, 320, 320].item(), 0)

    def test_rgb_release_allows_timeout_to_pass_original_without_affecting_model_input(self):
        from threading import Event
        from pipeworks.embedded import CudaAsync
        from pipeworks.execution import current_model_stream
        from pipeworks.models import Step

        item = self.frame()
        original = item.frame
        entered, unblock = Event(), Event()
        self.addCleanup(unblock.set)
        observed = []

        class SlowInference(Step):
            def process(inner, inputs):
                for working in inputs:
                    current_model_stream().synchronize()
                    observed.append(working.model_input)
                    entered.set()
                    unblock.wait(5)
                    working.model_output = None
                    yield working

        wrapper = CudaAsync(TensorRTPreProcess(), SlowInference(), TensorRTPostProcess(), timeout_ms=100)
        try:
            with patch.object(torch.Tensor, "clone", side_effect=AssertionError("input clone")):
                self.assertEqual(list(wrapper.process(iter([item]))), [item])
            self.assertTrue(entered.is_set())
            self.assertIs(item.frame, original)
            expected = observed[0].clone()
            with torch.cuda.stream(item.cuda_stream):
                item.frame.fill_(255)
            item.cuda_stream.synchronize()
            self.assertTrue(torch.equal(observed[0], expected))
            self.assertFalse(hasattr(item, "model_input"))
        finally:
            unblock.set()
            self.assertTrue(wrapper._session_lock.acquire(timeout=3))
            wrapper._session_lock.release()

    def test_postprocess_filters_nms_restores_coordinates(self):
        item = self.frame()
        next(TensorRTPreProcess().process(iter([item])))
        with torch.cuda.stream(item.cuda_stream):
            prediction = torch.zeros((1, 84, 10), device="cuda")
            prediction[0, :4, :3] = torch.tensor([[320, 320, 320], [320, 320, 320], [320, 320, 320], [160, 160, 160]], device="cuda")
            prediction[0, 6, 0] = .9
            prediction[0, 6, 1] = .8
            prediction[0, 4, 2] = .95
        item.model_output = {"output0": prediction}
        step = TensorRTPostProcess()
        step.configure(SimpleNamespace(classes=[2]))
        with patch.object(torch.Tensor, "cpu", side_effect=AssertionError("CPU copy")), patch.object(
            torch.Tensor, "clone", side_effect=AssertionError("NMS input clone")
        ):
            next(step.process(iter([item])))
        item.cuda_stream.synchronize()
        self.assertEqual(len(item.detections.boxes), 1)
        self.assertTrue(item.detections.boxes.data.is_cuda)
        self.assertTrue(torch.allclose(item.detections.boxes.xyxy[0], torch.tensor([2, 1, 6, 3], device="cuda", dtype=torch.float32)))
        self.assertEqual(item.detections.names[2], "car")
        self.assertAlmostEqual(item.detections.boxes.conf[0].item(), .9, places=5)
        self.assertEqual(item.detections.boxes.cls[0].item(), 2)
        self.assertTrue(torch.equal(prediction[0, :4, 0], torch.tensor([160, 240, 480, 400], device="cuda")))
        self.assertFalse(any(hasattr(item, name) for name in ("model_input", "model_output", "tensor_rt_transform", "model_cuda_stream")))
        from step.box_overlay import BoxOverlay
        overlay = BoxOverlay()
        overlay.configure(SimpleNamespace(line_width=1, line_color="#00ff00"))
        frame, detections = item.frame, item.detections
        self.assertIs(next(overlay.process(iter([item]))), item)
        item.cuda_stream.synchronize()
        self.assertIs(item.frame, frame)
        self.assertIs(item.detections, detections)
        self.assertEqual(item.frame[1, 2].item(), 145)
        self.assertEqual(item.frame[2, 4].item(), 16)
        next(TensorRTPreProcess().process(iter([item])))
        item.model_output = {"output0": torch.zeros_like(prediction)}
        next(step.process(iter([item])))
        self.assertEqual(len(item.detections.boxes), 0)
        item.model_output = None
        next(step.process(iter([item])))
        self.assertIsNone(item.detections)

    def test_postprocess_failure_also_cleans_buffers(self):
        item = self.frame()
        next(TensorRTPreProcess().process(iter([item])))
        item.model_output = {"wrong": torch.zeros(1, device="cuda")}
        with self.assertRaises(ValueError):
            next(TensorRTPostProcess().process(iter([item])))
        self.assertFalse(any(hasattr(item, name) for name in ("model_input", "model_output", "tensor_rt_transform", "model_cuda_stream")))

    def test_actual_plan_processing(self):
        from pipeworks.embedded import TensorRTInference
        plan = Path(__file__).resolve().parents[1] / "examples/model/yolo11n.plan"
        if not plan.is_file():
            self.skipTest("예제 엔진이 없습니다.")
        item = self.frame()
        next(TensorRTPreProcess().process(iter([item])))
        inference = TensorRTInference(plan)
        inference.configure(SimpleNamespace())
        list(inference.process(iter([item])))
        self.assertIsNotNone(item.model_output)
        next(TensorRTPostProcess().process(iter([item])))
        item.cuda_stream.synchronize()
        self.assertEqual(item.detections.orig_shape, (4, 8))


class ConfigurationTests(unittest.TestCase):
    def test_invalid_postprocess_configuration(self):
        for config in (SimpleNamespace(confidence=True), SimpleNamespace(iou=float("nan")), SimpleNamespace(classes=[80]), SimpleNamespace(max_det=0), SimpleNamespace(output_name="")):
            with self.subTest(config=config), self.assertRaises(ValueError):
                TensorRTPostProcess().configure(config)

