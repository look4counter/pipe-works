import sys
import tempfile
import unittest
from itertools import product
from pathlib import Path
from threading import Event
from unittest.mock import patch

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "examples")]
from step.tensor_rt_post_process import TensorRTPostProcess
from step.tensor_rt_pre_process import TensorRTPreProcess
from step.yolo_post_process import YoloPostProcess
from step.yolo_pre_process import YoloPreProcess

from pipeworks import Backend
from pipeworks.embedded import (
    CudaAsync,
    YoloInference,
    yolo_report,
)
from pipeworks.embedded.stream_report import report_scope
from pipeworks.inference_contract import bind_profile, inherited_profile
from pipeworks.models import PipelineContext, Step


class ContractTests(unittest.TestCase):
    def test_preprocessing_constructor_and_step_contract_match(self):
        options = dict(
            size=(32, 32),
            color_order="bgr",
            layout="nhwc",
            input_name="images",
            dtype="float16",
        )
        for cls in (YoloPreProcess, TensorRTPreProcess):
            step = cls(**options)
            self.assertEqual(cls.__bases__, (Step,))
            self.assertEqual(
                (step.input_name, step.layout, step.color_order),
                ("images", "nhwc", "bgr"),
            )

    def test_postprocessing_options_and_defaults_match(self):
        for cls in (YoloPostProcess, TensorRTPostProcess):
            self.assertIsNone(cls().classes)
            step = cls(names=["car", "person"], classes=[1], end2end=True)
            self.assertEqual(step.names, {0: "car", 1: "person"})
            self.assertTrue(step.end2end)


@unittest.skipUnless(torch.cuda.is_available(), "CUDA가 필요합니다.")
class CudaContractTests(unittest.TestCase):
    def frame(self):
        stream = torch.cuda.Stream()
        with torch.cuda.stream(stream):
            frame = torch.zeros((4, 8, 3), dtype=torch.uint8, device="cuda")
        return PipelineContext(frame=frame, pixel_format="RGB", cuda_stream=stream)

    def test_all_cross_processing_combinations_have_same_result(self):
        for pre_cls, post_cls in product(
            (YoloPreProcess, TensorRTPreProcess), (YoloPostProcess, TensorRTPostProcess)
        ):
            with self.subTest(pre=pre_cls.__name__, post=post_cls.__name__):
                item = self.frame()
                next(pre_cls(size=(32, 32), dtype="float16").process(iter([item])))
                self.assertTrue(hasattr(item, "image_transform"))
                self.assertFalse(hasattr(item, "yolo_transform"))
                self.assertFalse(hasattr(item, "tensor_rt_transform"))
                with torch.cuda.stream(item.cuda_stream):
                    prediction = torch.zeros(
                        (1, 6, 10), dtype=torch.float16, device="cuda"
                    )
                    prediction[0, :, 0] = prediction.new_tensor(
                        [16, 16, 16, 8, 0.9, 0.1]
                    )
                item.model_id = "model"
                item.model_output = {"output0": prediction}
                next(post_cls(names=["car", "person"]).process(iter([item])))
                boxes = item.detections["model"].boxes.data
                torch.testing.assert_close(boxes[0, :4], boxes.new_tensor([2, 1, 6, 3]))
                for name in (
                    "model_input",
                    "model_output",
                    "model_id",
                    "image_transform",
                    "_inference_profile",
                ):
                    self.assertFalse(hasattr(item, name), name)

    def test_yolo_named_input_single_and_shared(self):
        for batch in (False, True):
            item = self.frame()
            next(
                TensorRTPreProcess(size=(32, 32), input_name="images").process(
                    iter([item])
                )
            )
            tensor = item.model_input["images"]
            output = {"output0": torch.zeros((1, 84, 10), device="cuda")}
            with (
                patch("pipeworks.embedded.yolo_inference._Session") as session,
                patch(
                    "pipeworks.local_yolo_inference.infer", return_value=output
                ) as shared,
            ):
                session.return_value.infer.return_value = output
                self.assertIs(
                    next(YoloInference("model.pt", backend=Backend.TORCHSCRIPT, batch=batch).process(iter([item]))),
                    item,
                )
            self.assertIs(item.model_input["images"], tensor)
            if batch:
                self.assertIs(shared.call_args.args[1]["images"], tensor)
            else:
                self.assertIs(
                    session.return_value.infer.call_args.args[0]["images"], tensor
                )

    def test_yolo_rejects_ambiguous_named_inputs(self):
        item = self.frame()
        tensor = torch.zeros((1, 3, 32, 32), device="cuda")
        for inputs in ({"": tensor}, {}, {1: tensor}):
            item.model_input = inputs
            with self.assertRaises(ValueError):
                YoloInference("model.pt", backend=Backend.TORCHSCRIPT)._prepare_inputs(item)

    def test_real_backends_with_each_processing_pair_and_one_backend_profile(self):
        import ultralytics
        from ultralytics import YOLO

        config = Path(ultralytics.__file__).parent / "cfg/models/11/yolo11.yaml"
        plan = ROOT / "examples/model/yolo11n.plan"
        with tempfile.TemporaryDirectory() as directory:
            weights = Path(directory) / "test.pt"
            YOLO(str(config), task="detect", verbose=False).save(weights)
            backends = [
                (YoloInference, weights, "ULTRALYTICS", yolo_report, yolo_report)
            ]
            if plan.is_file():
                backends.append(
                    (
                        YoloInference,
                        plan,
                        "TensorRT",
                        yolo_report,
                        yolo_report,
                    )
                )
            for pre_cls, post_cls, batch, backend, both_active in product(
                (YoloPreProcess, TensorRTPreProcess),
                (YoloPostProcess, TensorRTPostProcess),
                (False, True),
                backends,
                (False, True),
            ):
                infer_cls, path, kind, report, other = backend
                with (
                    self.subTest(
                        pre=pre_cls.__name__,
                        post=post_cls.__name__,
                        backend=kind,
                        batch=batch,
                    ),
                    report_scope(),
                ):
                    stats = report.store()
                    stats.activate(kind)
                    other_kind = "TensorRT" if kind == "TORCHSCRIPT" else "TORCHSCRIPT"
                    other_stats = other.store()
                    if both_active:
                        other_stats.activate(other_kind)
                    item = self.frame()
                    # 제공된 TensorRT 모델은 입력 크기가 640으로 고정되어 있다.
                    size = (640, 640) if kind == "TensorRT" else (32, 32)
                    inputs = pre_cls(size=size).process(iter([item]))
                    options = (
                        {"backend": Backend.TENSORRT if kind == "TensorRT" else Backend.ULTRALYTICS}
                    )
                    outputs = infer_cls(
                        path, batch=batch, id="model", **options
                    ).process(inputs)
                    result = next(post_cls().process(outputs))
                    self.assertIs(result, item)
                    self.assertIn("model", result.detections)
                    snapshot = stats.snapshot(kind, 0)
                    self.assertEqual(snapshot["states"]["completed"], 1)
                    for stage in ("preprocess", "inference", "postprocess", "total"):
                        self.assertEqual(snapshot["recent"][stage][1], 1)
                    self.assertEqual(
                        other_stats.snapshot(other_kind, 0)["states"]["completed"], 0
                    )

    def test_mixed_async_timeout_and_busy_follow_actual_backend(self):
        for base, pre_cls, post_cls, kind, report, other_kind, other_report in (
            (
                YoloInference,
                TensorRTPreProcess,
                TensorRTPostProcess,
                "TORCHSCRIPT",
                yolo_report,
                "TensorRT",
                yolo_report,
            ),
            (
                YoloInference,
                YoloPreProcess,
                YoloPostProcess,
                "TensorRT",
                yolo_report,
                "TORCHSCRIPT",
                yolo_report,
            ),
        ):
            entered, unblock = Event(), Event()

            def slow_process(self, inputs):
                for item in inputs:
                    bind_profile(inherited_profile(item), kind)
                    entered.set()
                    unblock.wait(3)
                    item.model_output = None
                    yield item

            slow_type = type("SlowInference", (base,), {"process": slow_process})
            wrapper = CudaAsync(
                pre_cls(size=(32, 32)),
                slow_type(
                    "model.pt",
                    backend=Backend.TENSORRT if kind == "TensorRT" else Backend.TORCHSCRIPT,
                ),
                post_cls(),
                timeout_ms=100,
            )
            with report_scope():
                stats, other_stats = report.store(), other_report.store()
                stats.activate(kind)
                other_stats.activate(other_kind)
                items = [self.frame(), self.frame()]
                try:
                    self.assertEqual(list(wrapper.process(iter(items))), items)
                    self.assertTrue(entered.is_set())
                finally:
                    unblock.set()
                    self.assertTrue(wrapper._session_lock.acquire(timeout=3))
                    wrapper._session_lock.release()
                states = stats.snapshot(kind, 0)["states"]
                self.assertEqual(states["timeout"], 1)
                self.assertEqual(states["busy"], 1)
                self.assertEqual(states["partial"], 1)
                self.assertEqual(states["completed"], 0)
                self.assertEqual(
                    other_stats.snapshot(other_kind, 0)["states"]["timeout"], 0
                )
                self.assertEqual(
                    other_stats.snapshot(other_kind, 0)["states"]["busy"], 0
                )

    def test_legacy_profile_rebind_and_skipped_cleanup(self):
        for legacy in ("_yolo_profile", "_tensor_rt_profile"):
            with report_scope():
                stats = yolo_report.store()
                other = yolo_report.store()
                stats.activate("TORCHSCRIPT")
                other.activate("TensorRT")
                item = self.frame()
                next(TensorRTPreProcess(size=(32, 32)).process(iter([item])))
                profile = vars(item).pop("_inference_profile")
                setattr(item, legacy, profile)
                prediction = {"output0": torch.zeros((1, 84, 10), device="cuda")}
                with patch("pipeworks.embedded.yolo_inference._Session") as session:
                    session.return_value.infer.return_value = prediction
                    next(YoloInference("model.pt", backend=Backend.TORCHSCRIPT).process(iter([item])))
                next(TensorRTPostProcess().process(iter([item])))
                self.assertFalse(hasattr(item, legacy))
                self.assertEqual(stats.snapshot("TORCHSCRIPT", 0)["states"]["completed"], 1)
                self.assertEqual(
                    other.snapshot("TensorRT", 0)["states"]["completed"], 0
                )
                item.model_id = "model"
                item.model_output = None
                next(YoloPostProcess().process(iter([item])))
                self.assertIsNone(item.detections["model"])
                self.assertFalse(hasattr(item, "model_id"))

    def test_legacy_transform_inputs_and_error_cleanup(self):
        for legacy, post_cls in product(
            ("yolo_transform", "tensor_rt_transform"),
            (YoloPostProcess, TensorRTPostProcess),
        ):
            item = self.frame()
            next(YoloPreProcess(size=(32, 32)).process(iter([item])))
            transform = vars(item).pop("image_transform")
            setattr(item, legacy, transform)
            item.model_id = "model"
            item.model_output = {"output0": torch.zeros((1, 84, 10), device="cuda")}
            next(post_cls().process(iter([item])))
            self.assertEqual(item.detections["model"].orig_shape, (4, 8))
            self.assertFalse(hasattr(item, legacy))
            item.model_id = "model"
            item.model_input = object()
            item.image_transform = transform
            item.model_output = {"wrong": torch.zeros(1, device="cuda")}
            with self.assertRaises(ValueError):
                next(post_cls().process(iter([item])))
            self.assertFalse(hasattr(item, "image_transform"))
            self.assertFalse(hasattr(item, "model_input"))


if __name__ == "__main__":
    unittest.main()
