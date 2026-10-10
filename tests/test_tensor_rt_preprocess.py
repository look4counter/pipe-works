import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pipeworks import Pipeline
from pipeworks.embedded import TensorRTPreProcess
from pipeworks.execution import _frame_scope, _model_stream_scope
from pipeworks.models import PipelineContext


class ConfigurationTests(unittest.TestCase):
    def test_constructor_yaml_and_removal_restore_first_defaults(self):
        mean = [1, 2, 3]
        step = TensorRTPreProcess(size=(32, 48), mean=mean, dtype="float16")
        mean[0] = 99
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "stream.yml"
            config.write_text("TensorRTPreProcess:\n  size: [16, 24]\n  scale: 0\n", encoding="utf-8")
            Pipeline("preprocess", config=config).step(step)
        self.assertEqual(step.size, (16, 24))
        self.assertEqual(step.scale, 0)
        self.assertEqual(step.dtype, "float16")
        step.configure(SimpleNamespace())
        self.assertEqual(step.size, (32, 48))
        self.assertEqual(step.mean, (1, 2, 3))
        self.assertEqual(step.scale, 1 / 255)

    def test_rejects_invalid_settings_without_partial_update(self):
        invalid = [
            {"size": [0, 640]}, {"size": [True, 640]}, {"size": [640]},
            {"size": "640"}, {"size": [640.0, 640]}, {"size": None},
            {"resize_mode": "unknown"}, {"auto": 1}, {"stride": 0},
            {"stride": True}, {"center": "true"}, {"scaleup": 0},
            {"padding_value": 256}, {"padding_value": -1},
            {"padding_value": [0, 1]}, {"padding_value": [0, True, 1]},
            {"padding_value": float("nan")}, {"scale": float("inf")},
            {"scale": True}, {"mean": [0, 0]}, {"mean": [0, 0, float("nan")]},
            {"std": [1, 0, 1]}, {"std": [1, -1, 1]},
            {"dtype": "int8"}, {"layout": "chw"}, {"color_order": "gray"},
            {"input_name": ""}, {"input_name": 1},
            {"resize_mode": "stretch", "auto": True}, {"crop_size": [32, 32]},
            {"resize_mode": "resize_center_crop", "crop_size": [641, 640]},
            {"unknown": 1},
        ]
        step = TensorRTPreProcess(size=(32, 48))
        for options in invalid:
            with self.subTest(options=options), self.assertRaises(ValueError):
                step.configure(SimpleNamespace(**options))
            self.assertEqual(step.size, (32, 48))
        with self.assertRaises(ValueError):
            TensorRTPreProcess(std=(1, 0, 1))

    def test_cpu_input_is_rejected(self):
        item = PipelineContext(frame=torch.zeros((2, 2, 3), dtype=torch.uint8), pixel_format="RGB")
        with self.assertRaisesRegex(ValueError, "GPU"):
            next(TensorRTPreProcess().process(iter([item])))

    def test_old_example_reexports_embedded_class(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))
        from step.tensor_rt_pre_process import TensorRTPreProcess as ExamplePreProcess
        self.assertIs(ExamplePreProcess, TensorRTPreProcess)


@unittest.skipUnless(torch.cuda.is_available(), "CUDA가 필요합니다.")
class GpuTests(unittest.TestCase):
    def image(self, height=2, width=4, color=(10, 20, 30), pixel_format="RGB"):
        stream = torch.cuda.Stream()
        with torch.cuda.stream(stream):
            frame = torch.tensor(color, device="cuda", dtype=torch.uint8).expand(height, width, 3).contiguous()
        return PipelineContext(frame=frame, pixel_format=pixel_format, cuda_stream=stream)

    def run_step(self, item, **options):
        with patch.object(torch.Tensor, "cpu", side_effect=AssertionError("CPU copy")), patch.object(
            torch.Tensor, "numpy", side_effect=AssertionError("NumPy copy")
        ):
            self.assertIs(next(TensorRTPreProcess(**options).process(iter([item]))), item)
        self.assertTrue(item.model_input.is_cuda if isinstance(item.model_input, torch.Tensor)
                        else all(t.is_cuda for t in item.model_input.values()))
        return item

    def test_letterbox_padding_and_input_preserved(self):
        item = self.image()
        original = item.frame.clone()
        self.run_step(item, size=(8, 8), scale=1, padding_value=(40, 50, 60))
        self.assertEqual(tuple(item.model_input.shape), (1, 3, 8, 8))
        self.assertTrue(item.model_input.is_contiguous())
        self.assertTrue(torch.equal(item.frame, original))
        self.assertTrue(torch.equal(item.model_input[0, :, 0, 0], torch.tensor([40, 50, 60], device="cuda")))
        self.assertTrue(torch.equal(item.model_input[0, :, 3, 3], torch.tensor([10, 20, 30], device="cuda")))
        transform = item.tensor_rt_transform
        self.assertEqual((transform.ratio, transform.left, transform.top), (2, 0, 2))
        self.assertEqual(transform.ratio_xy, (2, 2))
        self.assertNotEqual(item.cuda_stream.cuda_stream, item.model_cuda_stream.cuda_stream)

    def test_auto_padding_rounding_and_scaleup(self):
        item = self.image(height=3, width=5)
        self.run_step(item, size=(8, 8), auto=True, stride=4)
        self.assertEqual(tuple(item.model_input.shape), (1, 3, 8, 8))
        self.assertEqual(item.tensor_rt_transform.top, 1)
        item = self.image(height=2, width=4)
        self.run_step(item, size=(8, 8), auto=True, stride=4)
        self.assertEqual(tuple(item.model_input.shape), (1, 3, 4, 8))
        self.assertEqual(item.tensor_rt_transform.output_shape, (4, 8))
        item = self.image(height=2, width=4)
        self.run_step(item, size=(8, 8), scaleup=False, center=False, scale=1)
        self.assertEqual(item.tensor_rt_transform.ratio, 1)
        self.assertEqual((item.tensor_rt_transform.left, item.tensor_rt_transform.top), (0, 0))
        self.assertEqual(item.model_input[0, 0, 0, 0].item(), 10)
        self.assertEqual(item.model_input[0, 0, 2, 0].item(), 114)

    def test_channel_normalization_fp16_nhwc_named_input(self):
        item = self.image(color=(10, 20, 30), pixel_format="BGR")
        self.run_step(item, size=(2, 4), resize_mode="stretch", scale=.1,
                      mean=(1, 1, 1), std=(2, 1, 2), dtype="float16", layout="nhwc",
                      input_name="pixels")
        output = item.model_input["pixels"]
        self.assertEqual(tuple(output.shape), (1, 2, 4, 3))
        self.assertEqual(output.dtype, torch.float16)
        self.assertTrue(output.is_contiguous())
        self.assertTrue(torch.allclose(output[0, 0, 0], torch.tensor([1, 1, 0], device="cuda", dtype=torch.float16)))
        item = self.image()
        self.run_step(item, size=(2, 4), resize_mode="stretch", color_order="bgr", scale=1)
        self.assertTrue(torch.equal(item.model_input[0, :, 0, 0], torch.tensor([30, 20, 10], device="cuda")))

    def test_stretch_has_separate_coordinate_scales(self):
        item = self.image()
        self.run_step(item, size=(6, 8), resize_mode="stretch")
        self.assertEqual(tuple(item.model_input.shape), (1, 3, 6, 8))
        self.assertEqual(item.tensor_rt_transform.ratio_xy, (2, 3))
        self.assertEqual((item.tensor_rt_transform.left, item.tensor_rt_transform.top), (0, 0))

    def test_center_crop_keeps_expected_pixels_and_coordinates(self):
        item = self.image(height=4, width=8)
        with torch.cuda.stream(item.cuda_stream):
            item.frame[:, :, 0] = torch.arange(8, device="cuda", dtype=torch.uint8)
        self.run_step(item, size=(4, 4), resize_mode="resize_center_crop", crop_size=(2, 4), scale=1)
        self.assertEqual(tuple(item.model_input.shape), (1, 3, 2, 4))
        self.assertTrue(torch.equal(item.model_input[0, 0, 0], torch.tensor([2, 3, 4, 5], device="cuda")))
        self.assertEqual((item.tensor_rt_transform.left, item.tensor_rt_transform.top), (-2, -1))
        item = self.image(height=4, width=8)
        self.run_step(item, size=(8, 8), resize_mode="resize_center_crop")
        self.assertEqual(item.tensor_rt_transform.ratio, 2)
        self.assertEqual(item.tensor_rt_transform.left, -4)

    def test_nv12_defaults_match_existing_conversion(self):
        from pipeworks.local_yolo import _nv12_to_rgb
        item = self.image()
        with torch.cuda.stream(item.cuda_stream):
            item.frame = torch.full((6, 8), 128, dtype=torch.uint8, device="cuda")
            item.frame[:4] = 80
        item.pixel_format = "NV12"
        item.video_stream = SimpleNamespace(codec_context=SimpleNamespace(height=4, width=8))
        item.cuda_stream.synchronize()
        expected = _nv12_to_rgb(item.frame)
        self.run_step(item, size=(4, 8))
        self.assertTrue(torch.allclose(item.model_input[0], expected, atol=1e-6))

    def test_frame_release_and_selected_stream_keep_storage_independent(self):
        item = self.image()
        stream = torch.cuda.Stream()
        released = []
        def release(event):
            self.assertIsNotNone(event)
            event.synchronize()
            with torch.cuda.stream(item.cuda_stream):
                item.frame.fill_(255)
            released.append(event)
        with _model_stream_scope(stream), _frame_scope(release):
            self.run_step(item, size=(2, 4), resize_mode="stretch", scale=1)
        self.assertIs(item.model_cuda_stream, stream)
        self.assertEqual(len(released), 1)
        self.assertEqual(item.model_input[0, 0, 0, 0].item(), 10)
        item.cuda_stream.synchronize()
        self.assertEqual(item.frame[0, 0, 0].item(), 255)

    def test_invalid_format_shape_and_stream(self):
        for kind in ("RGBA", "wrong_shape", "wrong_dtype", "NV12"):
            item = self.image()
            if kind == "wrong_shape":
                item.frame = item.frame[:, :, :2]
            elif kind == "wrong_dtype":
                item.frame = item.frame.float()
            else:
                item.pixel_format = kind
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                next(TensorRTPreProcess().process(iter([item])))
        if torch.cuda.device_count() > 1:
            item = self.image()
            with _model_stream_scope(torch.cuda.Stream(device=1)), self.assertRaises(ValueError):
                next(TensorRTPreProcess().process(iter([item])))


if __name__ == "__main__":
    unittest.main()
