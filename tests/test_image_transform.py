import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch

import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from pipeworks.embedded.tensor_rt_pre_process import TensorRTPreProcess
from pipeworks.image_transform import ImageTransform


class ImageTransformTests(unittest.TestCase):
    def test_preprocess_geometry_restores_original_boxes(self):
        # Expected scale/translation are independent fixtures for each mode.
        cases = [
            ({}, (2., 2.), (0, 2)),
            ({"center": False}, (2., 2.), (0, 0)),
            ({"auto": True, "stride": 3}, (2., 2.), (0, 0)),
            ({"scaleup": False}, (1., 1.), (4, 4)),
            ({"resize_mode": "stretch"}, (2., 3.), (0, 0)),
            ({"resize_mode": "resize_center_crop"}, (3., 3.), (-4, 0)),
            ({"resize_mode": "resize_center_crop", "crop_size": (8, 12)},
             (3., 3.), (-6, -2)),
        ]
        devices = ["cpu"] + (["cuda"] if torch.cuda.is_available() else [])
        for device in devices:
            for options, ratios, offsets in cases:
                with self.subTest(device=device, options=options):
                    step = TensorRTPreProcess(size=(12, 16), **options)
                    _, transform = step._resize(torch.zeros(3, 4, 8, device=device))
                    self.assertIsInstance(transform, ImageTransform)
                    expected = torch.tensor([[2., 1., 6., 3., .9, 2.]], device=device)
                    boxes = expected.clone()
                    boxes[:, 0:4:2].mul_(ratios[0]).add_(offsets[0])
                    boxes[:, 1:4:2].mul_(ratios[1]).add_(offsets[1])
                    pointer, dtype = boxes.data_ptr(), boxes.dtype
                    with patch.object(torch.Tensor, "cpu", side_effect=AssertionError("CPU copy")):
                        self.assertIs(transform.restore_boxes_(boxes), boxes)
                    torch.testing.assert_close(boxes, expected)
                    self.assertEqual(boxes.data_ptr(), pointer)
                    self.assertEqual(boxes.dtype, dtype)

    def test_clipping_empty_and_extra_columns(self):
        devices = ["cpu"] + (["cuda"] if torch.cuda.is_available() else [])
        transform = ImageTransform((4, 8), (2., 3.), 1, -2, (12, 16), "stretch")
        for device in devices:
            for dtype in (torch.float16, torch.float32):
                with self.subTest(device=device, dtype=dtype):
                    boxes = torch.tensor([[-3., -8., 21., 16., .5, 7.]],
                                         device=device, dtype=dtype)
                    transform.restore_boxes_(boxes)
                    torch.testing.assert_close(boxes, boxes.new_tensor([[0., 0., 8., 4., .5, 7.]]))
                    for columns in (4, 6):
                        empty = torch.empty((0, columns), device=device, dtype=dtype)
                        self.assertIs(transform.restore_boxes_(empty), empty)
                        self.assertEqual(empty.shape, (0, columns))

    def test_metadata_is_immutable_and_ratio_is_compatible(self):
        transform = ImageTransform((4, 8), (2., 2.), 0, 2, (12, 16), "letterbox")
        self.assertEqual(transform.ratio, 2.)
        self.assertEqual(ImageTransform((4, 8), (2., 3.), 0, 0, (12, 16), "stretch").ratio, (2., 3.))
        with self.assertRaises(FrozenInstanceError):
            transform.left = 3


if __name__ == "__main__":
    unittest.main()
