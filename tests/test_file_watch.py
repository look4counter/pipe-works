import os
import pickle
import sys
import tempfile
import time
from threading import Event, Thread
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pipeworks.file_watch import FileSubscription, _WatchService


class FakeObserver:
    def __init__(self):
        self.running = False
        self.watches = []
        self.emitters = ()

    def schedule(self, handler, path, recursive=False):
        watch = (handler, path)
        self.watches.append(watch)
        return watch

    def unschedule(self, watch):
        self.watches.remove(watch)

    def start(self):
        self.running = True

    def is_alive(self):
        return self.running

    def stop(self):
        self.running = False

    def join(self, timeout=None):
        pass


class FileWatchTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "step.py"
        self.path.write_bytes(b"first")
        self.service = _WatchService(observer_factory=FakeObserver)
        self.addCleanup(self.directory.cleanup)
        self.addCleanup(self.service.close)

    def subscribe(self):
        subscription = FileSubscription(self.path, service=self.service)
        self.addCleanup(subscription.close)
        return subscription

    def test_idle_and_shared_read(self):
        first, second = self.subscribe(), self.subscribe()
        first.snapshot()
        with patch.object(Path, "read_bytes", autospec=True, side_effect=Path.read_bytes) as read:
            for _ in range(1000):
                self.assertEqual(first.snapshot(), second.snapshot())
            self.assertEqual(read.call_count, 0)
            self.path.write_bytes(b"second")
            self.service.mark_changed(self.path)
            self.assertEqual(first.snapshot(), second.snapshot())
            self.assertEqual(read.call_count, 1)
        self.assertEqual(len(self.service.directories), 1)

    def test_callback_does_not_wait_for_service_lock(self):
        subscription = self.subscribe()
        subscription.snapshot()
        done = Event()
        def callback():
            self.service.mark_changed(self.path)
            done.set()
        with self.service.lock:
            thread = Thread(target=callback)
            thread.start()
            completed = done.wait(timeout=1)
        thread.join(timeout=1)
        self.assertTrue(completed)

    def test_config_consumers_share_snapshot_and_recover_silent_loss(self):
        from pipeworks.pipeline import _LiveConfig
        from hashlib import sha256
        self.path.write_bytes(b"Step:\n  offset: 1\n")
        digest = sha256(self.path.read_bytes()).hexdigest()
        with patch("pipeworks.file_watch._shared_service", return_value=self.service):
            first = _LiveConfig(self.path, {"Step": {"offset": 1}}, digest)
            second = _LiveConfig(self.path, {"Step": {"offset": 1}}, digest)
            self.addCleanup(first.close)
            self.addCleanup(second.close)
            first.section("Step")
            second.section("Step")
            with patch.object(Path, "read_bytes", autospec=True, side_effect=Path.read_bytes) as read:
                for _ in range(1000):
                    first.last_check = second.last_check = float("-inf")
                    first.section("Step")
                    second.section("Step")
                self.assertEqual(read.call_count, 0)
                self.path.write_bytes(b"Step:\n  offset: 2\n")
                self.service.mark_changed(self.path)
                first.last_check = second.last_check = float("-inf")
                self.assertEqual(first.section("Step").offset, 2)
                self.assertEqual(second.section("Step").offset, 2)
                self.assertEqual(read.call_count, 1)
            self.path.write_bytes(b"Step:\n  offset: 3\n")
            first.last_check = float("-inf")
            with patch("pipeworks.file_watch.monotonic", return_value=time.monotonic() + 31):
                self.assertEqual(first.section("Step").offset, 3)

    def test_silent_loss_with_preserved_metadata(self):
        subscription = self.subscribe()
        before = subscription.snapshot()
        stat = self.path.stat()
        self.path.write_bytes(b"other")
        os.utime(self.path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        self.assertEqual(subscription.snapshot(), before)
        with patch("pipeworks.file_watch.monotonic", return_value=time.monotonic() + 31):
            self.assertEqual(subscription.snapshot().source, b"other")

    def test_read_failure_remains_retryable(self):
        subscription = self.subscribe()
        subscription.snapshot()
        self.path.unlink()
        self.service.mark_changed(self.path)
        with self.assertRaises(OSError):
            subscription.snapshot()
        self.path.write_bytes(b"restored")
        self.assertEqual(subscription.snapshot().source, b"restored")

    def test_unrelated_directory_events_do_not_invalidate_file(self):
        from watchdog.events import DirModifiedEvent, FileModifiedEvent
        subscription = self.subscribe()
        subscription.snapshot()
        with patch.object(Path, "read_bytes", autospec=True, side_effect=Path.read_bytes) as read:
            self.service.handler.dispatch(DirModifiedEvent(str(self.path.parent)))
            self.service.handler.dispatch(FileModifiedEvent(str(self.path.with_name("other.py"))))
            subscription.snapshot()
            self.assertEqual(read.call_count, 0)

    def test_garbage_collection_releases_subscription(self):
        import gc
        subscription = FileSubscription(self.path, service=self.service)
        subscription.snapshot()
        observer = self.service.observer
        del subscription
        gc.collect()
        self.assertFalse(observer.is_alive())
        self.assertEqual(self.service.entries, {})

    def test_last_subscription_releases_observer(self):
        first, second = self.subscribe(), self.subscribe()
        first.snapshot()
        second.snapshot()
        observer = self.service.observer
        first.close()
        self.assertTrue(observer.is_alive())
        second.close()
        self.assertFalse(observer.is_alive())
        self.assertEqual(self.service.entries, {})
        self.assertEqual(self.service.directories, {})

    def test_dead_observer_recovers(self):
        subscription = self.subscribe()
        subscription.snapshot()
        self.service.observer.stop()
        self.path.write_bytes(b"changed")
        self.assertEqual(subscription.snapshot().source, b"changed")
        self.assertTrue(self.service.observer.is_alive())

    def test_registration_failure_falls_back(self):
        with patch.object(FakeObserver, "schedule", side_effect=OSError("unavailable")):
            with self.assertLogs("pipeworks.file_watch", level="WARNING"):
                subscription = self.subscribe()
                subscription.snapshot()
        self.path.write_bytes(b"fallback")
        with patch("pipeworks.file_watch.monotonic", return_value=time.monotonic() + 1):
            self.assertEqual(subscription.snapshot().source, b"fallback")

    def test_pickle_has_no_os_resources(self):
        subscription = self.subscribe()
        subscription.snapshot()
        restored = pickle.loads(pickle.dumps(subscription))
        self.addCleanup(restored.close)
        self.assertEqual(restored.snapshot().source, b"first")

    def test_actual_os_events_and_atomic_replace(self):
        service = _WatchService()
        self.addCleanup(service.close)
        subscription = FileSubscription(self.path, service=service)
        self.addCleanup(subscription.close)
        subscription.snapshot()
        for contents, replace in [(b"saved", False), (b"replaced", True)]:
            if replace:
                temporary = self.path.with_suffix(".tmp")
                temporary.write_bytes(contents)
                os.replace(temporary, self.path)
            else:
                self.path.write_bytes(contents)
            deadline = time.monotonic() + 5
            while subscription.snapshot().source != contents:
                if time.monotonic() >= deadline:
                    self.fail("OS 변경 알림이 전달되지 않았습니다.")
                time.sleep(0.01)


if __name__ == "__main__":
    unittest.main()
