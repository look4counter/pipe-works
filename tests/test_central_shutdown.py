from contextlib import nullcontext
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Event, Thread
import time
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, Mock, patch
from uuid import uuid4

import cloudpickle

from pipeworks import Pipeline
import pipeworks.main as main
from pipeworks.remote_logging import capture_settings


class SlowCleanupPipeline(Pipeline):
    def _run_local(self, stop_event=None):
        directory = self.config_path.parent
        (directory / "started").write_text(str(os.getpid()), encoding="utf-8")
        if not stop_event.wait(20):
            raise TimeoutError("중단 신호를 받지 못했습니다.")
        (directory / "cleaning").touch()
        deadline = time.monotonic() + 30
        while not (directory / "release").exists():
            if time.monotonic() >= deadline:
                raise TimeoutError("테스트 정리 장벽이 해제되지 않았습니다.")
            time.sleep(0.02)
        (directory / "cleaned").touch()


class QuickPipeline(Pipeline):
    def _run_local(self, stop_event=None):
        (self.config_path.parent / "quick-complete").touch()


def request_payload(pipeline):
    return cloudpickle.dumps({
        "pipeline": pipeline,
        "logging": capture_settings(),
        "execution_id": uuid4().hex,
    })


class HandlerCleanupTests(unittest.TestCase):
    def check_cleanup_wait(self, mode):
        entered, stopped, release, returned = Event(), Event(), Event(), Event()
        events, errors = [], []
        pipeline = Pipeline.__new__(Pipeline)
        pipeline.name = "cleanup-unit"

        def run(stop):
            entered.set()
            if stop.wait(2):
                stopped.set()
            release.wait(3)
            events.append("pipeline-cleaned")

        pipeline._run_local = run
        connection = MagicMock()

        def poll(timeout):
            if not entered.wait(2):
                raise TimeoutError("실행 작업자가 시작되지 않았습니다.")
            if mode == "disconnect":
                raise EOFError()
            if mode == "error":
                raise ValueError("연결 감시 오류")
            return False

        connection.poll.side_effect = poll
        writer, route = Mock(), Mock()
        writer.close.side_effect = lambda: events.append("writer-closed")
        route.close.side_effect = lambda: events.append("route-closed")

        def handle():
            try:
                main._handle(connection, b"request")
            except Exception as error:
                errors.append(error)
            finally:
                events.append("handler-returned")
                returned.set()

        clock = iter((0.0, 3.0))
        with (
            patch.object(main.cloudpickle, "loads", return_value={
                "pipeline": pipeline, "logging": {}, "execution_id": "unit",
            }),
            patch.object(main, "_install_output"),
            patch.object(main, "_use_output_writer", side_effect=lambda writer: nullcontext()),
            patch.object(main, "time", SimpleNamespace(monotonic=lambda: next(clock))),
            patch("pipeworks.remote_logging.install_relay"),
            patch("pipeworks.remote_logging.LogRoute", return_value=route),
            patch("pipeworks.remote_logging.PrintAdapter", return_value=writer),
        ):
            runner = Thread(target=handle, daemon=True)
            runner.start()
            try:
                self.assertTrue(stopped.wait(1), "정리 전에 중단 신호가 전달되어야 합니다.")
                self.assertFalse(returned.wait(0.1), "정리 중 요청을 해제하면 안 됩니다.")
            finally:
                release.set()
                runner.join(4)
            self.assertFalse(runner.is_alive())
        self.assertEqual(events, [
            "pipeline-cleaned", "writer-closed", "route-closed", "handler-returned",
        ])
        if mode == "error":
            self.assertEqual(len(errors), 1)
            self.assertIsInstance(errors[0], ValueError)
        else:
            self.assertEqual(errors, [])

    def test_disconnect_waits_for_pipeline_and_log_cleanup(self):
        self.check_cleanup_wait("disconnect")

    def test_heartbeat_timeout_waits_for_pipeline_and_log_cleanup(self):
        self.check_cleanup_wait("heartbeat")

    def test_monitor_error_stops_and_waits_before_releasing_request(self):
        self.check_cleanup_wait("error")


@unittest.skipUnless(os.name == "nt", "Windows 중앙 프로세스가 필요합니다.")
class CentralShutdownTests(unittest.TestCase):
    def wait_for_file(self, path, timeout=5):
        deadline = time.monotonic() + timeout
        while not path.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertTrue(path.exists(), f"파일이 생성되지 않았습니다: {path.name}")

    def test_slow_cleanup_keeps_server_alive_and_accepts_new_execution(self):
        cloudpickle.register_pickle_by_value(sys.modules[__name__])
        self.addCleanup(cloudpickle.unregister_pickle_by_value, sys.modules[__name__])
        with TemporaryDirectory() as temporary:
            directory = Path(temporary)
            config = directory / "config.yml"
            config.write_text("{}", encoding="utf-8")
            payload = request_payload(SlowCleanupPipeline("slow-cleanup", config=config))
            group = "test-cleanup-" + uuid4().hex
            main._start_server(group)
            process = main._launched_servers[-1]
            connection = None
            try:
                connection = main._connect(group)
                connection.send_bytes(payload)
                self.wait_for_file(directory / "started")
                connection.close()
                connection = None
                self.wait_for_file(directory / "cleaning")
                # 기존 10초 정리 대기와 1초 유휴 지연을 모두 넘긴다.
                deadline = time.monotonic() + 12
                while time.monotonic() < deadline:
                    self.assertIsNone(process.poll(), "정리 중 서버가 종료되었습니다.")
                    time.sleep(0.05)
                self.assertFalse((directory / "cleaned").exists())

                with main._connect(group) as ping:
                    ping.send_bytes(b"ping")
                    self.assertTrue(ping.poll(3))
                    self.assertEqual(ping.recv(), (
                        "pong", int((directory / "started").read_text(encoding="utf-8")),
                    ))
                with main._connect(group) as other:
                    other.send_bytes(request_payload(QuickPipeline("quick", config=config)))
                    self.assertTrue(other.poll(5))
                    self.assertEqual(other.recv(), ("ok", None))
                self.assertTrue((directory / "quick-complete").exists())
                self.assertIsNone(process.poll())

                (directory / "release").touch()
                self.wait_for_file(directory / "cleaned")
                self.assertEqual(process.wait(timeout=5), 0)
            finally:
                (directory / "release").touch()
                if connection is not None:
                    connection.close()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    process.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
