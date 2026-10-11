import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "examples")]
from pipeworks import Pipeline
from pipeworks.embedded import CudaAsync, TensorRTInference, TensorRTPreProcess
from pipeworks.models import PipelineContext, Step
from step.box_overlay import BoxOverlay
from step.tensor_rt_post_process import TensorRTPostProcess


class IdConfigurationTests(unittest.TestCase):
    def test_default_explicit_yaml_and_removal(self):
        self.assertEqual(TensorRTInference("models/yolo.plan").id, "yolo.plan")
        step = TensorRTInference("models/yolo.plan", id="vehicle")
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "stream.yml"
            config.write_text("TensorRTInference:\n  id: person\n", encoding="utf-8")
            Pipeline("ids", config=config).step(step)
        self.assertEqual(step.id, "person")
        step.configure(SimpleNamespace(id=None))
        self.assertEqual(step.id, "yolo.plan")
        step.configure(SimpleNamespace())
        self.assertEqual(step.id, "vehicle")

    def test_invalid_id_does_not_partially_apply(self):
        step = TensorRTInference("model.plan", id="original", gpu_id=1)
        for value in ("", " \t", True, 4, [], {}):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "id"):
                    TensorRTInference("model.plan", id=value)
                with self.assertRaisesRegex(ValueError, "id"):
                    step.configure(SimpleNamespace(id=value, gpu_id=0))
                self.assertEqual((step.id, step.gpu_id), ("original", 1))
                with self.assertRaisesRegex(ValueError, "id"):
                    BoxOverlay().configure(SimpleNamespace(id=value))

    def test_id_is_forwarded_even_when_processing_is_mocked(self):
        step = TensorRTInference("models/yolo.plan", id="vehicle")
        item = PipelineContext(model_output=None)
        with patch.object(step, "_process", side_effect=lambda inputs: inputs):
            self.assertEqual(list(step.process(iter([item]))), [item])
        self.assertEqual(item.model_id, "vehicle")


@unittest.skipUnless(torch.cuda.is_available(), "CUDA가 필요합니다.")
class ModelIdGpuTests(unittest.TestCase):
    def frame(self, detections=None):
        stream = torch.cuda.Stream()
        with torch.cuda.stream(stream):
            frame = torch.full((12, 8), 16, device="cuda", dtype=torch.uint8)
            frame[8:] = 128
        return PipelineContext(frame=frame, detections=detections, cuda_stream=stream,
                               pixel_format="NV12", video_stream=SimpleNamespace(
                                   codec_context=SimpleNamespace(height=8, width=8)))

    def prediction(self, item, model_id, score=.9):
        next(TensorRTPreProcess(size=(8, 8)).process(iter([item])))
        with torch.cuda.stream(item.model_cuda_stream):
            prediction = torch.zeros((1, 84, 10), device="cuda")
            prediction[0, :4, 0] = prediction.new_tensor([3., 3., 2., 2.])
            prediction[0, 6, 0] = score
        item.model_cuda_stream.synchronize()
        item.model_id = model_id
        item.model_output = {"output0": prediction}

    def test_results_preserved_replaced_skipped_and_isolated(self):
        item = self.frame()
        post = TensorRTPostProcess()
        self.prediction(item, "vehicle")
        next(post.process(iter([item])))
        original_mapping = item.detections
        vehicle = item.detections["vehicle"]
        self.prediction(item, "person")
        self.assertIs(item.detections, original_mapping)
        next(post.process(iter([item])))
        self.assertIs(item.detections["vehicle"], vehicle)
        self.assertEqual(set(original_mapping), {"vehicle"})
        self.assertEqual(set(item.detections), {"vehicle", "person"})
        person = item.detections["person"]
        self.prediction(item, "vehicle", score=.7)
        next(post.process(iter([item])))
        self.assertIsNot(item.detections["vehicle"], vehicle)
        self.assertIs(item.detections["person"], person)
        self.assertAlmostEqual(item.detections["vehicle"].boxes.conf[0].item(), .7, places=5)
        item.model_id, item.model_output = "vehicle", None
        next(post.process(iter([item])))
        self.assertIsNone(item.detections["vehicle"])
        self.assertIs(item.detections["person"], person)
        self.assertFalse(hasattr(item, "model_id"))

    def test_error_clears_only_current_id_and_cleans_buffers(self):
        prior = object()
        item = self.frame({"person": prior, "vehicle": prior})
        shared = item.detections
        self.prediction(item, "vehicle")
        item.model_output = {"wrong": torch.zeros(1, device="cuda")}
        with self.assertRaises(ValueError):
            next(TensorRTPostProcess().process(iter([item])))
        self.assertIs(item.detections["person"], prior)
        self.assertIsNone(item.detections["vehicle"])
        self.assertIs(shared["vehicle"], prior)
        for name in ("model_id", "model_input", "model_output", "tensor_rt_transform", "model_cuda_stream"):
            self.assertFalse(hasattr(item, name))

    def test_output_without_id_is_rejected(self):
        item = self.frame()
        self.prediction(item, "vehicle")
        del item.model_id
        with self.assertRaisesRegex(ValueError, "model_id"):
            next(TensorRTPostProcess().process(iter([item])))
        self.assertFalse(hasattr(item, "model_output"))

    def test_batch_and_interval_forward_ids(self):
        for batch in (False, True):
            with self.subTest(batch=batch):
                step = TensorRTInference("unused.plan", batch=batch, id="person", inference_interval_frame=2)
                items = [self.frame() for _ in range(3)]
                for item in items:
                    item.model_input = torch.ones((1, 2), device="cuda")
                class Session:
                    def __init__(self, *args):
                        pass
                    def infer(self, *args):
                        return {"output": torch.ones(1, device="cuda")}
                    def close(self):
                        pass
                with patch.object(step, "_model_settings", return_value=()), patch(
                    "pipeworks.embedded.tensor_rt_inference._EngineSession", Session
                ), patch("pipeworks.local_tensor_rt.infer", return_value={"output": torch.ones(1, device="cuda")}):
                    list(step.process(iter(items)))
                self.assertEqual([item.model_id for item in items], ["person"] * 3)
                self.assertEqual([item.model_output is None for item in items], [False, True, False])

    def test_same_engine_serial_results_and_original_input(self):
        plan = ROOT / "examples/model/yolo11n.plan"
        if not plan.is_file():
            self.skipTest("예제 엔진이 없습니다.")
        item = self.frame()
        item.cuda_stream.synchronize()
        original = item.frame.clone()
        for model_id in ("vehicle", "person", "vehicle"):
            next(TensorRTPreProcess().process(iter([item])))
            torch.testing.assert_close(item.frame, original)
            list(TensorRTInference(plan, id=model_id).process(iter([item])))
            next(TensorRTPostProcess().process(iter([item])))
        self.assertEqual(set(item.detections), {"vehicle", "person"})
        for result in item.detections.values():
            self.assertEqual(result.orig_shape, (8, 8))
            self.assertTrue(result.boxes.data.is_cuda)

    def result(self, coords):
        return SimpleNamespace(boxes=SimpleNamespace(xyxy=torch.tensor(coords, device="cuda", dtype=torch.float32).reshape(-1, 4)))

    def test_overlay_selects_all_or_one_id(self):
        for selected in (None, "vehicle", "person", "unknown"):
            with self.subTest(selected=selected):
                item = self.frame({"vehicle": self.result([[0, 0, 1, 1]]),
                                   "person": self.result([[5, 5, 6, 6]])})
                torch.cuda.synchronize()
                overlay = BoxOverlay()
                overlay.configure(SimpleNamespace(id=selected, line_width=1, keep_previous=False))
                next(overlay.process(iter([item])))
                item.cuda_stream.synchronize()
                self.assertEqual(item.frame[0, 0].item() == 145, selected in (None, "vehicle"))
                self.assertEqual(item.frame[5, 5].item() == 145, selected in (None, "person"))

    def test_overlay_keeps_previous_per_id_and_empty_clears_one(self):
        overlay = BoxOverlay()
        overlay.configure(SimpleNamespace(line_width=1))
        items = [
            self.frame({"vehicle": self.result([[0, 0, 1, 1]]), "person": self.result([[5, 5, 6, 6]])}),
            self.frame({"vehicle": None, "person": self.result([])}),
            self.frame({"vehicle": self.result([]), "person": None}),
        ]
        torch.cuda.synchronize()
        list(overlay.process(iter(items)))
        for item in items:
            item.cuda_stream.synchronize()
        self.assertEqual(items[1].frame[0, 0].item(), 145)
        self.assertEqual(items[1].frame[5, 5].item(), 16)
        self.assertEqual(items[2].frame[:8].max().item(), 16)

    def test_overlay_reuses_all_ids_when_async_has_no_results(self):
        overlay = BoxOverlay()
        overlay.configure(SimpleNamespace(line_width=1))
        first = self.frame({"vehicle": self.result([[0, 0, 1, 1]]),
                            "person": self.result([[5, 5, 6, 6]])})
        missing = self.frame()
        del missing.detections
        torch.cuda.synchronize()
        list(overlay.process(iter([first, missing])))
        missing.cuda_stream.synchronize()
        self.assertEqual(missing.frame[0, 0].item(), 145)
        self.assertEqual(missing.frame[5, 5].item(), 145)

    def test_async_timeout_does_not_mutate_original_mapping(self):
        from threading import Event
        entered, unblock = Event(), Event()
        prior = object()
        item = self.frame({"person": prior})
        original = item.detections
        self.addCleanup(unblock.set)

        class Slow(Step):
            def configure(self, config):
                pass
            def process(self, inputs):
                for working in inputs:
                    working.model_id, working.model_output = "vehicle", None
                    entered.set()
                    unblock.wait(5)
                    yield working

        wrapper = CudaAsync(TensorRTPreProcess(), Slow(), TensorRTPostProcess(), timeout_ms=100)
        try:
            list(wrapper.process(iter([item])))
            self.assertTrue(entered.is_set())
            unblock.set()
            self.assertTrue(wrapper._session_lock.acquire(timeout=3))
            wrapper._session_lock.release()
            self.assertIs(item.detections, original)
            self.assertEqual(set(original), {"person"})
        finally:
            unblock.set()

    def test_serial_async_model_groups_preserve_both_results(self):
        class SyntheticInference(Step):
            def __init__(self, model_id):
                self.model_id = model_id
            def configure(self, config):
                pass
            def process(self, inputs):
                for item in inputs:
                    item.model_id = self.model_id
                    with torch.cuda.stream(item.model_cuda_stream):
                        prediction = torch.zeros((1, 84, 10), device="cuda")
                        prediction[0, :4, 0] = prediction.new_tensor([3., 3., 2., 2.])
                        prediction[0, 6, 0] = .9
                    item.model_output = {"output0": prediction}
                    yield item

        item = self.frame()
        item.cuda_stream.synchronize()
        original = item.frame.clone()
        for model_id in ("vehicle", "person"):
            wrapper = CudaAsync(TensorRTPreProcess(size=(8, 8)),
                                SyntheticInference(model_id), TensorRTPostProcess(), timeout_ms=2000)
            self.assertEqual(list(wrapper.process(iter([item]))), [item])
        self.assertEqual(set(item.detections), {"vehicle", "person"})
        torch.testing.assert_close(item.frame, original)
        overlay = BoxOverlay()
        overlay.configure(SimpleNamespace())
        next(overlay.process(iter([item])))
        item.cuda_stream.synchronize()
        self.assertFalse(torch.equal(item.frame, original))


if __name__ == "__main__":
    unittest.main()
