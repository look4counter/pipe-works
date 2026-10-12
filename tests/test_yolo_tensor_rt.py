import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "examples")]
from pipeworks import Backend
from pipeworks.embedded import CudaAsync, YoloInference
from pipeworks.models import PipelineContext


class ConfigurationTests(unittest.TestCase):
    def test_enum_and_yaml_profile_reset(self):
        self.assertEqual(Backend.TENSORRT.value, "tensorrt")
        step = YoloInference("model.plan", backend=Backend.TENSORRT, profile_index=2)
        step.configure(SimpleNamespace(backend="tensorrt", profile_index=1))
        self.assertIs(step.backend, Backend.TENSORRT)
        self.assertEqual(step.profile_index, 1)
        step.configure(SimpleNamespace())
        self.assertEqual(step.profile_index, 2)
        for value in (-1, True, 1.5):
            with self.subTest(value=value), self.assertRaises(ValueError):
                step.configure(SimpleNamespace(profile_index=value))
        self.assertEqual(step.profile_index, 2)

    def test_profile_is_tensor_rt_only(self):
        with self.assertRaisesRegex(ValueError, "profile_index"):
            YoloInference("model.pt", backend=Backend.ULTRALYTICS, profile_index=1)

    def test_removed_tensor_rt_inference_api(self):
        import importlib.util
        from pipeworks import embedded

        self.assertFalse(hasattr(embedded, "TensorRTInference"))
        self.assertNotIn("TensorRTInference", embedded.__all__)
        self.assertIsNone(
            importlib.util.find_spec("pipeworks.embedded.tensor_rt_inference")
        )


@unittest.skipUnless(torch.cuda.is_available(), "CUDA가 필요합니다.")
class GpuTests(unittest.TestCase):
    def frame(self):
        stream = torch.cuda.Stream()
        with torch.cuda.stream(stream):
            frame = torch.zeros(32, 32, 3, device="cuda", dtype=torch.uint8)
        return PipelineContext(frame=frame, pixel_format="RGB", cuda_stream=stream)

    def test_actual_single_shared_engine_and_complete_report(self):
        from pipeworks.embedded.stream_report import report_scope
        from pipeworks.embedded.yolo_report import store
        from step.yolo_pre_process import YoloPreProcess
        from step.yolo_post_process import YoloPostProcess

        model = ROOT / "examples/model/yolo11n.plan"
        if not model.is_file():
            self.skipTest("예제 엔진이 없습니다.")
        for batch in (False, True):
            with self.subTest(batch=batch), report_scope():
                stats = store()
                item = self.frame()
                pre = YoloPreProcess().process(iter([item]))
                infer = YoloInference(model, backend=Backend.TENSORRT, batch=batch, id="vehicle").process(pre)
                from contextlib import redirect_stdout
                from io import StringIO
                from pipeworks.embedded import YoloReport

                reported = YoloReport().process(YoloPostProcess().process(infer))
                with redirect_stdout(StringIO()):
                    result = next(reported)
                self.assertIs(result, item)
                self.assertTrue(result.detections["vehicle"].boxes.data.is_cuda)
                snapshot = stats.snapshot("TensorRT", 0)
                self.assertEqual(snapshot["states"]["completed"], 1)
                for stage in ("preprocess", "inference", "postprocess", "total"):
                    self.assertEqual(snapshot["recent"][stage][1], 1)
                with redirect_stdout(StringIO()):
                    reported.close()
                self.assertFalse(stats.enabled("TensorRT"))
                infer.close()

    def test_shared_backend_loader_runs_tensor_rt(self):
        from pipeworks.embedded.yolo_inference import _Session

        model = ROOT / "examples/model/yolo11n.plan"
        if not model.is_file():
            self.skipTest("예제 엔진이 없습니다.")
        stream = torch.cuda.Stream()
        with torch.cuda.stream(stream):
            inputs = torch.zeros(1, 3, 640, 640, device="cuda")
            session = _Session(model, 0, Backend.TENSORRT)
            try:
                outputs = session.infer(inputs, stream)
                stream.synchronize()
                self.assertTrue(outputs)
                self.assertTrue(all(value.is_cuda for value in outputs.values()))
            finally:
                session.backend.close()

    def test_async_busy_and_timeout_use_unified_report(self):
        from threading import Event
        from pipeworks.embedded.stream_report import report_scope
        from pipeworks.embedded.yolo_report import store

        entered, unblock = Event(), Event()

        class Slow(YoloInference):
            def process(self, inputs):
                for item in inputs:
                    from pipeworks.execution import release_frame

                    release_frame()
                    entered.set()
                    unblock.wait(3)
                    yield item

        step = Slow("unused.plan", backend=Backend.TENSORRT)
        wrapper = CudaAsync(step, timeout_ms=100)
        with report_scope():
            stats = store()
            stats.activate("TensorRT")
            items = [self.frame(), self.frame()]
            try:
                results = list(wrapper.process(iter(items)))
                self.assertEqual(len(results), len(items))
                for result, item in zip(results, items):
                    self.assertIs(result.frame, item.frame)
                self.assertTrue(entered.is_set())
            finally:
                unblock.set()
                self.assertTrue(wrapper._session_lock.acquire(timeout=3))
                wrapper._session_lock.release()
            states = stats.snapshot("TensorRT", 0)["states"]
            self.assertEqual(states["timeout"], 1)
            self.assertEqual(states["busy"], 1)


if __name__ == "__main__":
    unittest.main()
