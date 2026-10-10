from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock
import time
import unittest
from unittest.mock import Mock, patch

from pipeworks.model_worker import get_model_worker


class ModelWorkerTests(unittest.TestCase):
    def setUp(self):
        self.workers, self.paths = {}, {}
        self.lock = Lock()
        self.create = Mock(side_effect=lambda path: object())

    def get(self, path):
        return get_model_worker(path, self.workers, self.paths, self.lock, self.create)

    def test_cached_worker_does_not_resolve_or_check_deleted_file(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "model.plan"
            path.write_bytes(b"engine")
            worker = self.get(path)
            self.create.assert_called_once_with(path.resolve())
            path.unlink()
            with patch.object(Path, "resolve", side_effect=AssertionError("resolve")), patch.object(
                Path, "is_file", side_effect=AssertionError("is_file")
            ):
                self.assertIs(self.get(path), worker)
            self.create.assert_called_once()

    def test_new_alias_shares_existing_worker_even_after_file_deletion(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "sub").mkdir()
            path = root / "model.plan"
            path.write_bytes(b"engine")
            worker = self.get(path)
            path.unlink()
            with patch.object(Path, "is_file", side_effect=AssertionError("is_file")):
                self.assertIs(self.get(root / "sub/../model.plan"), worker)
            self.create.assert_called_once()

    def test_relative_path_is_separate_for_each_working_directory(self):
        with TemporaryDirectory() as directory:
            roots = [Path(directory) / name for name in ("first", "second")]
            for root in roots:
                root.mkdir()
                (root / "model.plan").write_bytes(b"engine")
            with patch.object(Path, "cwd", return_value=roots[0]):
                first = self.get(Path("model.plan"))
            with patch.object(Path, "cwd", return_value=roots[1]):
                second = self.get(Path("model.plan"))
            self.assertIsNot(first, second)
            with patch.object(Path, "cwd", return_value=roots[0]), patch.object(
                Path, "resolve", side_effect=AssertionError("resolve")
            ):
                self.assertIs(self.get(Path("model.plan")), first)

    def test_missing_file_is_not_cached_and_can_be_created_later(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "model.plan"
            with self.assertRaises(FileNotFoundError):
                self.get(path)
            self.assertEqual(self.paths, {})
            self.create.assert_not_called()
            path.write_bytes(b"engine")
            self.get(path)
            self.create.assert_called_once()

    def test_failed_factory_is_not_cached_and_can_be_retried(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "model.plan"
            path.write_bytes(b"engine")
            worker = object()
            self.create.side_effect = [RuntimeError("startup failed"), worker]
            with self.assertRaisesRegex(RuntimeError, "startup failed"):
                self.get(path)
            self.assertEqual(self.workers, {})
            self.assertEqual(self.paths, {})
            self.assertIs(self.get(path), worker)

    def test_concurrent_first_calls_create_one_worker(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "model.plan"
            path.write_bytes(b"engine")
            worker = object()
            def create(path):
                time.sleep(.02)
                return worker
            self.create.side_effect = create
            with ThreadPoolExecutor(8) as executor:
                results = list(executor.map(self.get, [path] * 8))
            self.assertTrue(all(result is worker for result in results))
            self.create.assert_called_once()

    def test_cleared_worker_registry_rechecks_cached_path(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "model.plan"
            path.write_bytes(b"engine")
            self.get(path)
            self.workers.clear()
            path.unlink()
            with self.assertRaises(FileNotFoundError):
                self.get(path)
