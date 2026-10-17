import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

import torch
from ultralytics.utils.nms import non_max_suppression

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "examples")]
from step.yolo_post_process import YoloPostProcess
from step.yolo_pre_process import ImageTransform


class NmsTests(unittest.TestCase):
    def test_matches_reference(self):
        devices = ["cpu"] + (["cuda"] if torch.cuda.is_available() else [])
        for device in devices:
            for count in (0, 6, 10, 8400, 30001):
                generator = torch.Generator(device=device).manual_seed(42)
                prediction = torch.rand(
                    (1, 84, count), generator=generator, device=device
                )
                prediction[:, :4] *= 640
                prediction[:, 4:] *= 0.3
                for classes in (None, [], [2], [2, 5, 2]):
                    with self.subTest(device=device, count=count, classes=classes):
                        step = YoloPostProcess()
                        step.configure(SimpleNamespace(classes=classes, max_det=15))
                        reference = prediction.clone()
                        if count == 6:
                            # 라이브러리가 텐서 형태에 따라 자동으로 end2end 분기를 선택하지 않도록 한다.
                            reference = torch.cat((reference, reference.new_zeros((1, 84, 1))), dim=2)
                        expected = non_max_suppression(
                            reference,
                            step.confidence,
                            step.iou,
                            classes=classes,
                            max_det=15,
                            nc=80,
                        )[0]
                        actual = step._nms(prediction.clone())
                        torch.testing.assert_close(
                            actual, expected, rtol=1e-5, atol=1e-5
                        )

    def test_best_class_precedes_class_filter_and_threshold_is_strict(self):
        prediction = torch.zeros((1, 84, 10))
        prediction[:, :4] = 10
        prediction[0, 6, 0] = 0.8
        prediction[0, 5, 0] = 0.9
        prediction[0, 6, 1] = 0.25
        prediction[0, 6, 2] = 0.7
        step = YoloPostProcess()
        step.configure(SimpleNamespace(classes=[2]))
        result = step._nms(prediction)
        self.assertEqual(result.shape, (1, 6))
        self.assertAlmostEqual(result[0, 4].item(), 0.7, places=6)

    def test_coordinate_slices_match_reference(self):
        boxes = torch.tensor([[-20.0, 30.0, 900.0, 500.0, 0.9, 2.0]])
        transform = ImageTransform(
            shape=(100, 200),
            ratio_xy=(2.0, 2.0),
            left=10,
            top=20,
            output_shape=(240, 420),
            resize_mode="letterbox",
        )
        expected = boxes.clone()
        expected[:, [0, 2]] = ((expected[:, [0, 2]] - 10) / 2).clamp(0, 200)
        expected[:, [1, 3]] = ((expected[:, [1, 3]] - 20) / 2).clamp(0, 100)
        transform.restore_boxes_(boxes)
        torch.testing.assert_close(boxes, expected)

    def test_threshold_endpoints_ties_and_reconfiguration(self):
        devices = ["cpu"] + (["cuda"] if torch.cuda.is_available() else [])
        step = YoloPostProcess()
        for device in devices:
            prediction = torch.zeros((1, 84, 20), device=device)
            prediction[:, :4] = 10
            prediction[:, 4:6] = 0.5  # 클래스 점수가 같으면 가장 작은 인덱스를 선택한다.
            for confidence, iou, classes in ((0, 0, [0]), (0.5, 0.7, None), (1, 1, [])):
                step.configure(
                    SimpleNamespace(
                        confidence=confidence, iou=iou, classes=classes, max_det=1
                    )
                )
                expected = non_max_suppression(
                    prediction.clone(),
                    confidence,
                    iou,
                    classes=classes,
                    max_det=1,
                    nc=80,
                )[0]
                torch.testing.assert_close(step._nms(prediction.clone()), expected)


if __name__ == "__main__":
    unittest.main()
