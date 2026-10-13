import runpy
import sys
import tempfile
import unittest
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import patch

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "examples")]

from step.yolo_post_process import YoloPostProcess
from step.yolo_pre_process import YoloPreProcess

from pipeworks import Backend
from pipeworks import Pipeline
from pipeworks.embedded import CudaAsync, YoloInference
from pipeworks.embedded.stream_report import report_scope
from pipeworks.embedded.yolo_report import span, store
from step.yolo_pre_process import ImageTransform
from pipeworks.models import PipelineContext, Step


class ConfigurationTests(unittest.TestCase):
    def test_preprocess_import_is_independent_of_tensor_rt_example(self):
        from importlib.util import module_from_spec, spec_from_file_location

        spec = spec_from_file_location(
            "independent_yolo_pre_process", ROOT / "examples/step/yolo_pre_process.py"
        )
        module = module_from_spec(spec)
        with patch.dict(sys.modules, {"step.tensor_rt_pre_process": None}):
            spec.loader.exec_module(module)
            self.assertEqual(module.YoloPreProcess.__bases__, (Step,))
            self.assertEqual(module.YoloPreProcess().size, (640, 640))

    def test_defaults_match_yolo_inference(self):
        pre, post = YoloPreProcess(), YoloPostProcess()
        self.assertEqual(pre.size, (640, 640))
        self.assertEqual(
            (pre.color_order, pre.layout, pre.input_name), ("rgb", "nchw", None)
        )
        self.assertEqual(pre.dtype, "float32")
        self.assertIsNone(post.classes)
        self.assertEqual((post.confidence, post.iou, post.max_det), (0.25, 0.7, 300))
        self.assertEqual(len(post.names), 80)

    def test_constructor_yaml_and_reset(self):
        pre = YoloPreProcess(size=(64, 64))
        post = YoloPostProcess(names=["vehicle", "person"], classes=[0])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "stream.yml"
            path.write_text(
                "YoloPreProcess:\n  size: [32, 32]\nYoloPostProcess:\n  classes: [1]\n  confidence: 0.6\n",
                encoding="utf-8",
            )
            Pipeline("yolo-processing", config=path).step(pre).step(post)
        self.assertEqual(pre.size, (32, 32))
        self.assertEqual(post.classes, [1])
        self.assertEqual(post.confidence, 0.6)
        pre.configure(SimpleNamespace())
        post.configure(SimpleNamespace())
        self.assertEqual(pre.size, (64, 64))
        self.assertEqual(post.classes, [0])
        self.assertEqual(post.names, {0: "vehicle", 1: "person"})

    def test_preprocess_rejects_incompatible_options(self):
        for config in (
            {"layout": "hwc"},
            {"color_order": "gray"},
            {"input_name": ""},
            {"size": [0, 640]},
            {"unknown": True},
        ):
            with self.subTest(config=config), self.assertRaises(ValueError):
                YoloPreProcess().configure(SimpleNamespace(**config))

    def test_invalid_postprocess_settings_preserve_previous_config(self):
        post = YoloPostProcess(names=["a", "b"], classes=[1])
        for config in (
            {"confidence": float("nan")},
            {"confidence": True},
            {"iou": 2},
            {"classes": [2]},
            {"classes": [-1]},
            {"classes": [True]},
            {"max_det": 0},
            {"output_name": " "},
            {"names": []},
            {"names": {1: "a"}},
            {"names": [""]},
            {"end2end": 1},
            {"unknown": True},
        ):
            with self.subTest(config=config), self.assertRaises(ValueError):
                post.configure(SimpleNamespace(**config))
            self.assertEqual(post.classes, [1])
            self.assertEqual(post.names, {0: "a", 1: "b"})

    def test_example_builds_with_yolo_steps_and_report(self):
        module = runpy.run_path(str(ROOT / "examples/01_single_stream_rtsp_style.py"))
        pipeline = module["build_pipeline"]()
        self.assertIsNotNone(pipeline)
        self.assertIn("YoloPreProcess", module)
        self.assertIn("YoloPostProcess", module)


@unittest.skipUnless(torch.cuda.is_available(), "CUDA가 필요합니다.")
class ProcessingTests(unittest.TestCase):
    def frame(self, pixel_format="NV12"):
        stream = torch.cuda.Stream()
        with torch.cuda.stream(stream):
            if pixel_format == "NV12":
                frame = torch.full((6, 8), 128, dtype=torch.uint8, device="cuda")
                frame[:4] = 16
            else:
                frame = torch.zeros((4, 8, 3), dtype=torch.uint8, device="cuda")
                frame[..., 0 if pixel_format == "RGB" else 2] = 255
        return PipelineContext(
            frame=frame,
            pixel_format=pixel_format,
            cuda_stream=stream,
            video_stream=SimpleNamespace(
                codec_context=SimpleNamespace(height=4, width=8)
            ),
        )

    def output_context(self, dtype=torch.float32, count=10):
        item = self.frame()
        with torch.cuda.stream(item.cuda_stream):
            prediction = torch.zeros((1, 6, count), dtype=dtype, device="cuda")
            if count:
                prediction[0, :, 0] = torch.tensor(
                    [16, 16, 16, 8, 0.9, 0.1], device="cuda"
                )
            if count > 1:
                prediction[0, :, 1] = torch.tensor(
                    [16, 16, 16, 8, 0.8, 0.1], device="cuda"
                )
            if count > 2:
                prediction[0, :, 2] = torch.tensor(
                    [16, 16, 16, 8, 0.1, 0.85], device="cuda"
                )
        item.model_id = "vehicle"
        item.model_input = object()
        item.model_output = {"output0": prediction}
        item.image_transform = ImageTransform(
            (4, 8), (4, 4), 0, 8, (32, 32), "letterbox"
        )
        return item

    def assert_clean(self, item):
        for name in (
            "model_input",
            "model_output",
            "model_id",
            "image_transform",
            "_inference_profile",
        ):
            self.assertFalse(hasattr(item, name), name)

    def test_preprocess_letterbox_and_frame_release(self):
        item = self.frame()
        item.cuda_stream.synchronize()
        original = item.frame.clone()
        with (
            patch("step.yolo_pre_process.release_frame") as release,
            patch.object(torch.Tensor, "cpu", side_effect=AssertionError("CPU copy")),
        ):
            self.assertIs(
                next(YoloPreProcess(size=(32, 32)).process(iter([item]))), item
            )
        release.assert_called_once()
        self.assertTrue(release.call_args.kwargs["ready_event"].query())
        self.assertEqual(item.model_input.shape, (1, 3, 32, 32))
        self.assertEqual(item.model_input.dtype, torch.float32)
        self.assertEqual(item.image_transform.shape, (4, 8))
        self.assertAlmostEqual(item.model_input[0, 0, 0, 0].item(), 114 / 255, places=5)
        self.assertEqual(item.model_input[0, 0, 16, 16].item(), 0)
        self.assertTrue(torch.equal(item.frame, original))
        self.assertFalse(hasattr(item, "tensor_rt_transform"))

    def test_rgb_bgr_and_fp16(self):
        for pixel_format in ("RGB", "BGR"):
            with self.subTest(pixel_format=pixel_format):
                item = self.frame(pixel_format)
                next(YoloPreProcess(size=(4, 8), dtype="float16").process(iter([item])))
                self.assertEqual(item.model_input.dtype, torch.float16)
                self.assertTrue(torch.all(item.model_input[0, 0] == 1))
                self.assertTrue(torch.all(item.model_input[0, 1:] == 0))

    def test_preprocess_input_independent_of_released_frame(self):
        item = self.frame("RGB")
        next(YoloPreProcess(size=(4, 8)).process(iter([item])))
        expected = item.model_input.clone()
        with torch.cuda.stream(item.cuda_stream):
            item.frame.zero_()
        item.cuda_stream.synchronize()
        self.assertTrue(torch.equal(item.model_input, expected))

    def test_postprocess_nms_class_filter_and_coordinates(self):
        for dtype in (torch.float32, torch.float16):
            item = self.output_context(dtype=dtype)
            other = object()
            previous = {"other": other, "vehicle": object()}
            item.detections = previous
            with patch.object(
                torch.Tensor, "cpu", side_effect=AssertionError("CPU copy")
            ):
                result = next(
                    YoloPostProcess(names=["car", "person"], classes=[0]).process(
                        iter([item])
                    )
                )
            self.assertIs(result, item)
            self.assertIs(result.detections["other"], other)
            self.assertIsNot(result.detections, previous)
            boxes = result.detections["vehicle"].boxes.data
            self.assertEqual(boxes.shape, (1, 6))
            self.assertEqual(boxes.dtype, torch.float32)
            torch.testing.assert_close(
                boxes[0, :4], torch.tensor([2.0, 1.0, 6.0, 3.0], device="cuda")
            )
            self.assertEqual(
                result.detections["vehicle"].names, {0: "car", 1: "person"}
            )
            self.assert_clean(result)

    def test_default_all_classes_and_max_det(self):
        item = self.output_context()
        next(YoloPostProcess(names=["car", "person"]).process(iter([item])))
        self.assertEqual(item.detections["vehicle"].boxes.data.shape[0], 2)
        item = self.output_context()
        next(YoloPostProcess(names=["car", "person"], max_det=1).process(iter([item])))
        self.assertEqual(item.detections["vehicle"].boxes.data.shape[0], 1)

    def test_six_standard_candidates_and_empty_predictions(self):
        for count in (0, 6):
            item = self.output_context(count=count)
            next(
                YoloPostProcess(names=["car", "person"], classes=[0]).process(
                    iter([item])
                )
            )
            self.assertEqual(
                item.detections["vehicle"].boxes.data.shape[0], 0 if count == 0 else 1
            )

    def test_end2end_output(self):
        item = self.output_context()
        with torch.cuda.stream(item.cuda_stream):
            item.model_output = {
                "output0": torch.tensor(
                    [[[8, 12, 24, 20, 0.9, 1], [8, 12, 24, 20, 0.1, 0]]],
                    device="cuda",
                )
            }
        next(
            YoloPostProcess(names=["car", "person"], end2end=True).process(iter([item]))
        )
        boxes = item.detections["vehicle"].boxes.data
        self.assertEqual(boxes.shape, (1, 6))
        self.assertEqual(boxes[0, 5].item(), 1)
        torch.testing.assert_close(
            boxes[0, :4], torch.tensor([2.0, 1.0, 6.0, 3.0], device="cuda")
        )

    def test_skip_and_invalid_output_cleanup(self):
        item = self.output_context()
        item.model_output = None
        item.detections = {"other": object()}
        next(YoloPostProcess(names=["car", "person"]).process(iter([item])))
        self.assertIsNone(item.detections["vehicle"])
        self.assertIn("other", item.detections)
        self.assert_clean(item)
        item = self.output_context()
        item.model_output = {"output0": torch.zeros(1, 6, 10)}
        with self.assertRaises(ValueError):
            next(YoloPostProcess(names=["car", "person"]).process(iter([item])))
        self.assert_clean(item)

    def test_postprocess_error_finishes_profile_once(self):
        with report_scope():
            stats = store()
            stats.activate("TORCHSCRIPT")
            item = self.frame()
            next(YoloPreProcess(size=(32, 32)).process(iter([item])))
            item.model_id = "vehicle"
            item.model_output = {"wrong_name": torch.zeros(1, 6, 10, device="cuda")}
            with self.assertRaises(ValueError):
                next(YoloPostProcess(names=["a", "b"]).process(iter([item])))
            self.assert_clean(item)
            states = stats.snapshot("TORCHSCRIPT", 0)["states"]
            self.assertEqual(states["error"], 1)
            self.assertEqual(states["completed"], 0)

    def test_bad_preprocess_input_records_error(self):
        with report_scope():
            stats = store()
            stats.activate("TORCHSCRIPT")
            item = PipelineContext(
                frame=torch.zeros(4, 8, 3, dtype=torch.uint8), pixel_format="RGB"
            )
            with self.assertRaises(ValueError):
                next(YoloPreProcess().process(iter([item])))
            self.assertFalse(hasattr(item, "_inference_profile"))
            self.assertEqual(stats.snapshot("TORCHSCRIPT", 0)["states"]["error"], 1)

    def test_actual_model_single_and_shared_pipeline_has_one_complete_profile(self):
        import ultralytics
        from ultralytics import YOLO

        config = Path(ultralytics.__file__).parent / "cfg/models/11/yolo11.yaml"
        with tempfile.TemporaryDirectory() as directory:
            weights = Path(directory) / "test.pt"
            YOLO(str(config), task="detect", verbose=False).save(weights)
            for batch in (False, True):
                with self.subTest(batch=batch), report_scope():
                    stats = store()
                    stats.activate("ULTRALYTICS")
                    item = self.frame()
                    original = item.frame
                    pre = YoloPreProcess(size=(32, 32)).process(iter([item]))
                    inference = YoloInference(
                        weights, backend=Backend.ULTRALYTICS, batch=batch, id="vehicle"
                    ).process(pre)
                    result = next(YoloPostProcess().process(inference))
                    self.assertIs(result, item)
                    self.assertIs(result.frame, original)
                    self.assertEqual(result.detections["vehicle"].orig_shape, (4, 8))
                    self.assertEqual(
                        result.detections["vehicle"].boxes.data.shape[1], 6
                    )
                    self.assert_clean(result)
                    snapshot = stats.snapshot("ULTRALYTICS", 0)
                    self.assertEqual(snapshot["states"]["completed"], 1)
                    for stage in ("preprocess", "inference", "postprocess", "total"):
                        self.assertEqual(snapshot["recent"][stage][1], 1)

    def test_entire_pipeline_report_and_skipped_frames(self):
        def predict(tensor, stream):
            with span("inference", stream):
                output = torch.zeros((1, 6, 10), device=tensor.device)
            return {"output0": output}

        for batch in (False, True):
            with self.subTest(batch=batch), report_scope():
                stats = store()
                stats.activate("TORCHSCRIPT")
                frames = [self.frame(), self.frame()]
                from pipeworks.embedded import EveryNFrames
                post = EveryNFrames(
                    YoloPreProcess(size=(32, 32)),
                    YoloInference("model.pt", backend=Backend.TORCHSCRIPT, batch=batch),
                    YoloPostProcess(names=["car", "person"]),
                    interval_frames=2,
                ).process(iter(frames))

                def shared(path, tensor, gpu, **kwargs):
                    kwargs["on_inference_complete"](0.01)
                    return predict(tensor, torch.cuda.current_stream(gpu))

                with (
                    patch("pipeworks.embedded.yolo_inference._Session") as session,
                    patch("pipeworks.local_yolo_inference.infer", side_effect=shared),
                ):
                    session.return_value.infer.side_effect = predict
                    self.assertEqual(list(post), frames)
                states = stats.snapshot("TORCHSCRIPT", 0)
                self.assertEqual(states["states"]["completed"], 1)
                self.assertEqual(states["states"].get("skipped", 0), 0)
                for stage in ("preprocess", "inference", "postprocess"):
                    self.assertEqual(states["recent"][stage][1], 1)
                self.assertEqual(states["recent"]["inference"][1], 1)
                for item in frames:
                    self.assert_clean(item)

    def test_inference_error_finishes_shared_profile(self):
        with report_scope():
            stats = store()
            stats.activate("TORCHSCRIPT")
            item = self.frame()
            prepared = YoloPreProcess(size=(32, 32)).process(iter([item]))
            with (
                patch(
                    "pipeworks.embedded.yolo_inference._Session",
                    side_effect=RuntimeError("failed"),
                ),
                self.assertRaisesRegex(RuntimeError, "failed"),
            ):
                list(YoloInference("model.pt", backend=Backend.TORCHSCRIPT).process(prepared))
            self.assertEqual(stats.snapshot("TORCHSCRIPT", 0)["states"]["error"], 1)

    def test_async_timeout_records_partial_profile_and_preserves_frame(self):
        entered, unblock = Event(), Event()

        class Slow(Step):
            def configure(self, config):
                pass

            def process(self, inputs):
                for item in inputs:
                    entered.set()
                    unblock.wait(3)
                    item.model_output = None
                    yield item

        wrapper = CudaAsync(
            YoloPreProcess(size=(32, 32)), Slow(), YoloPostProcess(), timeout_ms=100
        )
        item = self.frame()
        original = item.frame
        with report_scope():
            stats = store()
            stats.activate("YOLO")
            try:
                self.assertEqual(list(wrapper.process(iter([item]))), [item])
                self.assertTrue(entered.is_set())
                self.assertIs(item.frame, original)
                self.assertFalse(hasattr(item, "model_input"))
            finally:
                unblock.set()
                self.assertTrue(wrapper._session_lock.acquire(timeout=3))
                wrapper._session_lock.release()
            states = stats.snapshot("YOLO", 0)["states"]
            self.assertEqual(states["timeout"], 1)
            self.assertEqual(states["partial"], 1)
            self.assertEqual(states["completed"], 0)


if __name__ == "__main__":
    unittest.main()
