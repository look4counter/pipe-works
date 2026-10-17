import sys
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "examples")]


class RemoteExampleDependenciesTests(unittest.TestCase):
    def test_reused_example_methods_restore_without_step_package(self):
        from pipeworks import Pipeline, main
        from pipeworks.embedded import CudaAsync, EveryNFrames
        from step.yolo_pre_process import YoloPreProcess
        from step.yolo_post_process import YoloPostProcess

        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            config = directory / "config.yml"
            config.write_text("{}", encoding="utf-8")
            pipeline = Pipeline("reused-methods", config=config).step(
                EveryNFrames(CudaAsync(YoloPreProcess(size=(8, 8)), YoloPostProcess(names=["object"])), interval_frames=3)
            )
            connection = Mock()
            connection.recv.return_value = ("ok", None)
            with patch.object(main, "_connect", return_value=connection):
                main.run_remote(pipeline)
            payload = directory / "pipeline.pkl"
            payload.write_bytes(connection.send_bytes.call_args_list[0].args[0])
            code = (
                "import sys, cloudpickle, torch; "
                "sys.modules['step'] = None; "
                "pipeline = cloudpickle.loads(open(sys.argv[1], 'rb').read())['pipeline']; "
                "pre, post = pipeline.steps[0].steps[0].steps; "
                "image, transform = pre._resize(torch.zeros(3, 4, 4)); "
                "assert tuple(image.shape) == (1, 3, 8, 8); "
                "assert transform.shape == (4, 4); "
                "assert tuple(post._nms(torch.zeros(1, 5, 0)).shape) == (0, 6)"
            )
            result = subprocess.run([sys.executable, "-c", code, str(payload)], cwd=ROOT, capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
