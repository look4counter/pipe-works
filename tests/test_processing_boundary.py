import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "examples")]


class ProcessingBoundaryTests(unittest.TestCase):
    def test_core_processing_modules_and_detect_are_removed(self):
        from pipeworks import embedded, local_yolo_inference

        for name in ("image", "image_transform", "image_preprocessing", "detection_postprocessing", "embedded.yolo_detect"):
            with self.subTest(name=name):
                self.assertIsNone(importlib.util.find_spec("pipeworks." + name))
        self.assertFalse(hasattr(embedded, "YoloDetect"))
        self.assertNotIn("YoloDetect", embedded.__all__)
        self.assertFalse(hasattr(local_yolo_inference, "infer_detection"))

    def test_examples_own_processing_implementation(self):
        from step.yolo_pre_process import YoloPreProcess
        from step.yolo_post_process import YoloPostProcess

        self.assertEqual(YoloPreProcess._pixels.__module__, "step.yolo_pre_process")
        self.assertEqual(YoloPreProcess._resize.__module__, "step.yolo_pre_process")
        self.assertEqual(YoloPostProcess._nms.__module__, "step.yolo_post_process")

    def test_core_imports_without_examples_or_yolo_library(self):
        code = (
            "import sys; "
            "sys.path.insert(0, 'src'); "
            "sys.modules['step'] = None; "
            "sys.modules['ultralytics'] = None; "
            "from pipeworks.embedded import YoloInference; "
            "from pipeworks import local_yolo_inference; "
            "assert callable(local_yolo_inference.infer)"
        )
        result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
