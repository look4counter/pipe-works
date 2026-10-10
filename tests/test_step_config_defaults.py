import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pipeworks import Pipeline
from pipeworks.embedded import (
    CudaAsync, NvidiaDecode, NvidiaEncode, RTSPPublish, RTSPSource,
    Tap, TensorRTInference, YoloDetect,
)
from pipeworks.hotswap import Hotswap
from pipeworks.models import Step


class StepConfigDefaultsTests(unittest.TestCase):
    def test_custom_step_can_opt_into_constructor_defaults(self):
        class CustomStep(Step):
            def __init__(self, *, threshold=.5):
                self._set_config_defaults(threshold=threshold)

            def configure(self, config):
                self.threshold = self._resolve_config(config).threshold

            def process(self, inputs):
                yield from inputs

        step = CustomStep(threshold=.7)
        step.configure(SimpleNamespace(threshold=0))
        self.assertEqual(step.threshold, 0)
        step.configure(SimpleNamespace())
        self.assertEqual(step.threshold, .7)

    def cases(self):
        return [
            (RTSPSource, ("rtsp://input",), {"reconnect": False, "reconnect_interval_ms": 100,
             "transport": "udp", "timeout_ms": 750}, {"reconnect": True, "timeout_ms": 0}),
            (RTSPPublish, ("rtsp://output",), {"reconnect": False, "reconnect_interval_ms": 100,
             "transport": "udp", "timeout_ms": 750, "packet_size": 1200}, {"packet_size": 1400}),
            (NvidiaDecode, (), {"gpu_id": 2}, {"gpu_id": 0}),
            (NvidiaEncode, (), {"gpu_id": 2, "fps": 15}, {"fps": 25}),
            (YoloDetect, (Path("model.pt"),), {"gpu_id": 2, "classes": [1], "confidence": .7,
             "inference_interval_frame": 3}, {"classes": [], "confidence": .4}),
            (TensorRTInference, (Path("model.engine"),), {"gpu_id": 2, "profile_index": 1,
             "inference_interval_frame": 3}, {"profile_index": 0}),
            (CudaAsync, (NvidiaDecode(),), {"timeout_ms": 25}, {"timeout_ms": 0}),
        ]

    def test_constructor_partial_yaml_and_removal(self):
        for cls, args, defaults, overrides in self.cases():
            with self.subTest(step=cls.__name__):
                step = cls(*args, **defaults)
                for config in (SimpleNamespace(), SimpleNamespace(**overrides), SimpleNamespace()):
                    step.configure(config)
                    expected = defaults | vars(config)
                    for name, value in expected.items():
                        self.assertEqual(getattr(step, name), value)

    def test_defaults_without_constructor_options(self):
        for step, expected in [
            (RTSPSource("input"), {"timeout_ms": 5000, "reconnect_interval_ms": 3000}),
            (RTSPPublish("output"), {"packet_size": 1452}),
            (NvidiaDecode(), {"gpu_id": 0}),
            (NvidiaEncode(), {"gpu_id": 0, "fps": 30}),
            (YoloDetect(Path("model.pt")), {"confidence": .25, "classes": None}),
            (TensorRTInference(Path("model.engine")), {"profile_index": 0}),
            (CudaAsync(NvidiaDecode()), {"timeout_ms": 5}),
        ]:
            with self.subTest(step=type(step).__name__):
                step.configure(SimpleNamespace())
                for name, value in expected.items():
                    self.assertEqual(getattr(step, name), value)

    def test_explicit_null_and_mutable_constructor_value(self):
        classes = [1]
        step = YoloDetect(Path("model.pt"), classes=classes)
        classes.append(2)
        step.classes.append(3)
        step.configure(SimpleNamespace(classes=None))
        self.assertIsNone(step.classes)
        step.configure(SimpleNamespace())
        self.assertEqual(step.classes, [1])

    def test_pipeline_registration_and_async_children(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "stream.yml"
            config.write_text("TensorRTInference:\n  profile_index: 0\nCudaAsync:\n  timeout_ms: 0\n", encoding="utf-8")
            inference = TensorRTInference(Path("model.engine"), gpu_id=2, profile_index=1)
            async_step = CudaAsync(inference, timeout_ms=25)
            Pipeline("test", config=config).step(async_step)
            self.assertEqual(async_step.timeout_ms, 0)
            self.assertEqual(inference.gpu_id, 2)
            self.assertEqual(inference.profile_index, 0)
            inference.configure(SimpleNamespace())
            self.assertEqual(inference.profile_index, 1)
            config.write_text("{}", encoding="utf-8")
            decoder = NvidiaDecode(gpu_id=2)
            Pipeline("test", config=config).step(decoder)
            self.assertEqual(decoder.gpu_id, 2)

    def test_tap_forwards_defaults_and_overrides(self):
        decoder = NvidiaDecode(gpu_id=2)
        tap = Tap(decoder)
        tap.configure(SimpleNamespace(gpu_id=0))
        self.assertEqual(decoder.gpu_id, 0)
        tap.configure(SimpleNamespace())
        self.assertEqual(decoder.gpu_id, 2)

    def test_invalid_reload_preserves_active_config_and_constructor_defaults(self):
        inference = TensorRTInference(Path("model.engine"), gpu_id=2, profile_index=1)
        wrapper = Hotswap(inference, watch_code=False)
        wrapper.configure(SimpleNamespace(gpu_id=3))
        with self.assertLogs("pipeworks.hotswap", level="ERROR"):
            wrapper._apply_config(SimpleNamespace(profile_index=None))
        self.assertEqual(inference.gpu_id, 3)
        self.assertEqual(inference.profile_index, 1)
        wrapper._apply_config(SimpleNamespace())
        self.assertEqual(inference.gpu_id, 2)
        self.assertEqual(inference.profile_index, 1)

    def test_invalid_constructor_values_use_existing_validation(self):
        for factory in [
            lambda: TensorRTInference(Path("model.engine"), profile_index=-1),
            lambda: YoloDetect(Path("model.pt"), confidence=0),
            lambda: NvidiaEncode(fps=0),
            lambda: RTSPSource("input", timeout_ms=None),
            lambda: RTSPPublish("output", reconnect_interval_ms=-1),
        ]:
            with self.subTest(factory=factory), self.assertRaises(ValueError):
                factory()


if __name__ == "__main__":
    unittest.main()
