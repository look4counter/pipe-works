import importlib.util
from pathlib import Path
from threading import Event, Thread
import time
import unittest
from unittest.mock import patch

from pipeworks.models import PipelineContext


class MetadataFromDBTests(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).resolve().parents[1] / "examples/step/metadata_from_db.py"
        spec = importlib.util.spec_from_file_location("metadata_shutdown_test", path)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.threads = []

        def start_thread(*args, **kwargs):
            thread = Thread(*args, **kwargs)
            self.threads.append(thread)
            return thread

        thread_patch = patch.object(self.module, "Thread", side_effect=start_thread)
        thread_patch.start()
        self.addCleanup(thread_patch.stop)
        self.step = self.module.MetadataFromDB()

    def assert_stopped(self):
        self.assertTrue(self.threads)
        self.assertTrue(all(not thread.is_alive() for thread in self.threads))

    def test_normal_input_end_stops_worker_and_preserves_frames(self):
        frames = [PipelineContext(), PipelineContext()]
        self.assertEqual(list(self.step.process(iter(frames))), frames)
        self.assert_stopped()

    def test_input_error_stops_worker_and_propagates(self):
        def inputs():
            yield PipelineContext()
            raise RuntimeError("input failed")

        with self.assertRaisesRegex(RuntimeError, "input failed"):
            list(self.step.process(inputs()))
        self.assert_stopped()

    def test_close_stops_worker_without_waiting_for_refresh_interval(self):
        output = self.step.process(iter([PipelineContext(), PipelineContext()]))
        next(output)
        self.assertTrue(self.threads[0].is_alive())
        started = time.monotonic()
        output.close()
        self.assertLess(time.monotonic() - started, 1)
        self.assert_stopped()

    def test_restart_does_not_leave_previous_worker_running(self):
        for _ in range(2):
            output = self.step.process(iter([PipelineContext()]))
            next(output)
            self.assertTrue(all(not thread.is_alive() for thread in self.threads[:-1]))
            output.close()
            self.assert_stopped()
        self.assertEqual(len(self.threads), 2)

    def test_worker_refreshes_metadata_before_close(self):
        class FastEvent(Event):
            def wait(self, timeout=None):
                self.assert_interval = timeout
                return super().wait(.01)

        stop = FastEvent()
        with patch.object(self.module, "Event", return_value=stop):
            output = self.step.process(iter([PipelineContext()]))
            next(output)
            try:
                deadline = time.monotonic() + 1
                while self.step.metadata.count == 0 and time.monotonic() < deadline:
                    Event().wait(.001)
                self.assertGreater(self.step.metadata.count, 0)
                self.assertEqual(stop.assert_interval, 3)
            finally:
                output.close()
        self.assert_stopped()
