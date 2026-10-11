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
from pipeworks import Pipeline
from pipeworks.embedded import CudaAsync, YoloDetect
from pipeworks.execution import current_model_stream, release_frame
from pipeworks.image_transform import ImageTransform
from pipeworks.models import PipelineContext
from step.box_overlay import BoxOverlay
from step.tensor_rt_post_process import TensorRTPostProcess


class YoloIdConfigurationTests(unittest.TestCase):
    def test_default_explicit_yaml_and_removal(self):
        for filename in ("model.pt", "model.engine"):
            self.assertEqual(YoloDetect(Path("models") / filename).id, filename)
        step = YoloDetect("models/yolo.pt", id="vehicle")
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "stream.yml"
            config.write_text("YoloDetect:\n  id: person\n", encoding="utf-8")
            Pipeline("ids", config=config).step(step)
        self.assertEqual(step.id, "person")
        step.configure(SimpleNamespace(id=None))
        self.assertEqual(step.id, "yolo.pt")
        step.configure(SimpleNamespace())
        self.assertEqual(step.id, "vehicle")

    def test_invalid_id_preserves_configuration(self):
        step = YoloDetect("model.pt", id="vehicle", gpu_id=1, confidence=.7)
        for value in ("", " \t", True, 4, [], {}):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "id"):
                    YoloDetect("model.pt", id=value)
                with self.assertRaisesRegex(ValueError, "id"):
                    step.configure(SimpleNamespace(id=value, gpu_id=0, confidence=.3))
                self.assertEqual((step.id, step.gpu_id, step.confidence), ("vehicle", 1, .7))


@unittest.skipUnless(torch.cuda.is_available(), "CUDA가 필요합니다.")
class YoloIdGpuTests(unittest.TestCase):
    def frame(self, detections=None):
        stream = torch.cuda.Stream()
        with torch.cuda.stream(stream):
            frame = torch.full((12, 8), 16, dtype=torch.uint8, device="cuda")
            frame[8:] = 128
        stream.synchronize()
        return PipelineContext(frame=frame, cuda_stream=stream, pixel_format="NV12",
                               detections=detections, video_stream=SimpleNamespace(
                                   codec_context=SimpleNamespace(height=8, width=8)))

    def run_mocked(self, step, items, side_effect):
        with patch("ultralytics.YOLO", return_value=object()), patch(
            "pipeworks.embedded.yolo_detect._predict", side_effect=side_effect
        ), patch("pipeworks.embedded.yolo_detect.infer", side_effect=side_effect):
            return list(step.process(iter(items)))

    def test_serial_ids_replace_only_selected_result_without_mutating_shared_mapping(self):
        for batch in (False, True):
            with self.subTest(batch=batch):
                tensor_result = object()
                item = self.frame({"tensor": tensor_result})
                original_frame = item.frame.clone()
                shared = item.detections
                first, second, replacement = object(), object(), object()
                for model_id, result in (("vehicle", first), ("person", second), ("vehicle", replacement)):
                    step = YoloDetect("same.pt", batch=batch, id=model_id)
                    self.run_mocked(step, [item], lambda *args, result=result, **kwargs: result)
                self.assertEqual(item.detections, {"tensor": tensor_result, "vehicle": replacement, "person": second})
                self.assertEqual(shared, {"tensor": tensor_result})
                torch.testing.assert_close(item.frame, original_frame)
                self.assertFalse(hasattr(item, "model_id"))

    def test_skipped_frames_keep_other_ids_and_clear_current_id(self):
        for batch in (False, True):
            with self.subTest(batch=batch):
                other, old, result = object(), object(), object()
                original = {"tensor": other, "vehicle": old}
                items = [self.frame(original) for _ in range(3)]
                step = YoloDetect("model.pt", batch=batch, id="vehicle", inference_interval_frame=2)
                self.run_mocked(step, items, lambda *args, **kwargs: result)
                self.assertEqual([item.detections["vehicle"] for item in items], [result, None, result])
                self.assertTrue(all(item.detections["tensor"] is other for item in items))
                self.assertEqual(original, {"tensor": other, "vehicle": old})

    def test_error_preserves_other_ids_and_existing_error_policy(self):
        for batch in (False, True):
            with self.subTest(batch=batch):
                prior = object()
                shared = {"tensor": prior, "vehicle": prior}
                item = self.frame(shared)
                step = YoloDetect("model.pt", batch=batch, id="vehicle")
                if batch:
                    with self.assertLogs("pipeworks.embedded.yolo_detect", level="ERROR"):
                        self.run_mocked(step, [item], RuntimeError("failed"))
                else:
                    with self.assertRaisesRegex(RuntimeError, "failed"):
                        self.run_mocked(step, [item], RuntimeError("failed"))
                self.assertEqual(item.detections, {"tensor": prior, "vehicle": None})
                self.assertEqual(shared, {"tensor": prior, "vehicle": prior})

    def test_id_change_during_inference_applies_to_next_input(self):
        for batch in (False, True):
            with self.subTest(batch=batch):
                step = YoloDetect("model.pt", batch=batch, id="first")
                first, second = self.frame(), self.frame()
                result = object()
                def inference(*args, **kwargs):
                    step.configure(SimpleNamespace(id="second"))
                    return result
                self.run_mocked(step, [first, second], inference)
                self.assertEqual(first.detections, {"first": result})
                self.assertEqual(second.detections, {"second": result})

    def test_legacy_mapping_error_is_explicit(self):
        for batch in (False, True):
            item = self.frame(object())
            with self.subTest(batch=batch), self.assertRaisesRegex(ValueError, "사전"):
                list(YoloDetect("model.pt", batch=batch).process(iter([item])))

    def test_yolo_and_tensor_rt_share_mapping_and_overlay(self):
        item = self.frame()
        result = SimpleNamespace(boxes=SimpleNamespace(xyxy=torch.tensor([[0., 0., 1., 1.]], device="cuda")))
        torch.cuda.synchronize()
        self.run_mocked(YoloDetect("same.pt", id="vehicle"), [item], lambda *args, **kwargs: result)
        with torch.cuda.stream(item.cuda_stream):
            prediction = torch.zeros((1, 84, 10), device="cuda")
            prediction[0, :4, 0] = prediction.new_tensor([5., 5., 2., 2.])
            prediction[0, 6, 0] = .9
        item.model_id = "person"
        item.model_output = {"output0": prediction}
        item.tensor_rt_transform = ImageTransform((8, 8), (1., 1.), 0, 0, (8, 8), "stretch")
        next(TensorRTPostProcess().process(iter([item])))
        self.assertIs(item.detections["vehicle"], result)
        overlay = BoxOverlay()
        overlay.configure(SimpleNamespace(line_width=1))
        next(overlay.process(iter([item])))
        item.cuda_stream.synchronize()
        self.assertEqual(item.frame[0, 0].item(), 145)
        self.assertEqual(item.frame[4, 4].item(), 145)

    def test_async_late_result_keeps_original_mapping_in_both_modes(self):
        for batch in (False, True):
            with self.subTest(batch=batch):
                entered, unblock = Event(), Event()
                prior = object()
                mapping = {"tensor": prior}
                item = self.frame(mapping)
                step = YoloDetect("model.pt", batch=batch, id="vehicle")
                def slow(*args, **kwargs):
                    ready = torch.cuda.Event()
                    ready.record(current_model_stream())
                    release_frame(ready_event=ready)
                    entered.set()
                    unblock.wait(5)
                    return object()
                wrapper = CudaAsync(step, timeout_ms=100)
                with patch("ultralytics.YOLO", return_value=object()), patch(
                    "pipeworks.embedded.yolo_detect._predict", side_effect=slow
                ), patch("pipeworks.embedded.yolo_detect.infer", side_effect=slow):
                    try:
                        self.assertEqual(list(wrapper.process(iter([item]))), [item])
                        self.assertTrue(entered.is_set())
                        unblock.set()
                        self.assertTrue(wrapper._session_lock.acquire(timeout=3))
                        wrapper._session_lock.release()
                        self.assertIs(item.detections, mapping)
                        self.assertEqual(mapping, {"tensor": prior})
                    finally:
                        unblock.set()

    def test_real_same_model_serial_preserves_results_and_frame(self):
        model_path = ROOT / "examples/model/yolo11n.pt"
        if not model_path.is_file():
            self.skipTest("실제 모델 파일이 필요합니다.")
        item = self.frame()
        original = item.frame.clone()
        for model_id in ("vehicle", "person"):
            list(YoloDetect(model_path, id=model_id).process(iter([item])))
        self.assertEqual(set(item.detections), {"vehicle", "person"})
        self.assertIsNot(item.detections["vehicle"], item.detections["person"])
        for result in item.detections.values():
            self.assertEqual(result.orig_shape, (8, 8))
            self.assertTrue(result.boxes.data.is_cuda)
        torch.testing.assert_close(item.frame, original)


if __name__ == "__main__":
    unittest.main()
