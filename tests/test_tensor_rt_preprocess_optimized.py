import itertools
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from pipeworks.embedded.tensor_rt_pre_process import TensorRTPreProcess


class OptimizedTests(unittest.TestCase):
    def test_reference_normalization_and_resize_options(self):
        devices = ["cpu"] + (["cuda"] if torch.cuda.is_available() else [])
        for device, mode, layout, dtype in itertools.product(
            devices, ["letterbox", "stretch", "resize_center_crop"],
            ["nchw", "nhwc"], ["float32", "float16"]
        ):
            with self.subTest(device=device, mode=mode, layout=layout, dtype=dtype):
                step = TensorRTPreProcess(size=(8, 10), resize_mode=mode,
                    layout=layout, dtype=dtype, scale=-.02,
                    mean=(1, -2, 3), std=(2, 3, .5), padding_value=(10, 20, 30))
                pixels = torch.rand((3, 6, 12), device=device) * 255
                resized, transform = step._resize(pixels)
                original = resized.clone()
                mean = resized.new_tensor(step.mean).view(1, 3, 1, 1)
                std = resized.new_tensor(step.std).view(1, 3, 1, 1)
                expected = (original * step.scale - mean) / std
                if layout == "nhwc":
                    expected = expected.permute(0, 2, 3, 1)
                expected = expected.to(getattr(torch, dtype)).contiguous()
                actual = step._normalize(resized)
                torch.testing.assert_close(actual, expected, rtol=1e-5, atol=1e-5)
                self.assertTrue(actual.is_contiguous())
                self.assertEqual(transform.output_shape, tuple(original.shape[-2:]))

    def test_same_size_does_not_interpolate(self):
        step = TensorRTPreProcess(size=(4, 6), resize_mode="stretch")
        with patch("pipeworks.embedded.tensor_rt_pre_process.F.interpolate",
                   side_effect=AssertionError("unnecessary resize")):
            result, _ = step._resize(torch.zeros(3, 4, 6))
        self.assertEqual(result.shape, (1, 3, 4, 6))

    def test_reconfigure_and_previous_output_independence(self):
        step = TensorRTPreProcess(scale=1, mean=(1, 2, 3))
        first = step._normalize(torch.full((1, 3, 2, 2), 10.))
        saved = first.clone()
        step.configure(SimpleNamespace(scale=0, mean=(4, 5, 6)))
        second = step._normalize(torch.full((1, 3, 2, 2), 20.))
        torch.testing.assert_close(first, saved)
        torch.testing.assert_close(second[0, :, 0, 0], torch.tensor([-4., -5., -6.]))


if __name__ == "__main__":
    unittest.main()
