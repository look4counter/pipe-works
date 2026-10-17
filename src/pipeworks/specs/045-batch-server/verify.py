from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "src"))
sys.dont_write_bytecode = True


class BatchServerTests(unittest.TestCase):
    def test_old_keyword_is_rejected(self):
        from pipeworks import Pipeline

        with self.assertRaisesRegex(TypeError, "batch_process"):
            Pipeline("old", config=Path("unused.yml"), batch_process="production")

    def test_remote_connection_uses_batch_server(self):
        from pipeworks.main import run_remote

        connection = Mock()
        connection.recv.return_value = ("ok", None)
        pipeline = SimpleNamespace(batch_server="camera-a", steps=[])
        with patch("pipeworks.main._connect", return_value=connection) as connect:
            run_remote(pipeline)
        connect.assert_called_once_with("camera-a")
        connection.close.assert_called_once_with()


def main():
    with TemporaryDirectory(prefix="batch-server-tests-") as temporary:
        directory = Path(temporary)
        for name in ("test_central_process", "test_pipeline_routing", "test_async"):
            original = (ROOT / "tests" / f"{name}.py").read_text(encoding="utf-8")
            (directory / f"{name}.py").write_text(
                original.replace("batch_process", "batch_server"), encoding="utf-8"
            )
        sys.path.insert(0, str(ROOT / "tests"))
        sys.path.insert(0, str(directory))
        loader = unittest.TestLoader()
        suite = loader.loadTestsFromTestCase(BatchServerTests)
        suite.addTests(loader.loadTestsFromNames([
            "test_central_process.CentralProcessTests.test_batch_server_constructor_contract",
            "test_pipeline_routing",
            "test_async",
        ]))
        result = unittest.TextTestRunner(verbosity=1).run(suite)
        return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
