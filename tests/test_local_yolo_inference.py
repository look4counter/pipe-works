import importlib.util
import unittest


class UnifiedModuleTests(unittest.TestCase):
    def test_only_unified_worker_module_remains(self):
        from pipeworks import local_yolo_inference as shared

        self.assertIsNone(importlib.util.find_spec("pipeworks.local_yolo"))
        self.assertIsNone(importlib.util.find_spec("pipeworks.local_tensor_rt"))
        self.assertTrue(callable(shared.infer))
        self.assertFalse(hasattr(shared, "infer_detection"))

    def test_profile_is_tensorrt_only(self):
        from unittest.mock import patch
        from pipeworks import local_yolo_inference as shared

        with patch.object(shared, "_validate_input"):
            for backend in ("torchscript", "ultralytics"):
                with self.assertRaisesRegex(ValueError, "profile_index"):
                    shared.infer("unused.pt", object(), backend=backend, profile_index=1)
