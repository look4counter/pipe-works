import os
import signal
from contextlib import redirect_stdout
from multiprocessing import get_context
import sys
import types
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import time
import unittest

import cloudpickle
import torch
from io import BytesIO, StringIO
from unittest.mock import patch

from pipeworks import Pipeline
from pipeworks.embedded import Tap, StreamReport
from pipeworks.main import _ADDRESS, _KEY, _connect, _server_executable, _start_server, _user_sid
from pipeworks.main import _server_endpoint, _LOCK_PATH, _launched_servers
from pipeworks.models import PipelineContext, Step


class RecordingSource(Step):
    def __init__(self, path: Path, *, continuous: bool = False):
        self.path = path
        self.continuous = continuous

    def configure(self, config):
        pass

    def process(self, inputs):
        self.path.write_text(str(os.getpid()), encoding="utf-8")
        try:
            while True:
                yield PipelineContext()
                if not self.continuous:
                    return
                time.sleep(0.02)
        finally:
            self.path.with_suffix(".closed").write_text("closed", encoding="utf-8")


class FailingSource(Step):
    def configure(self, config):
        pass

    def process(self, inputs):
        raise ValueError("expected failure")
        yield


class ProgressSource(RecordingSource):
    def process(self, inputs):
        for index, item in enumerate(super().process(inputs)):
            self.path.with_suffix(".progress").write_text(str(index), encoding="utf-8")
            yield item


class PrintingSource(Step):
    def __init__(self, message: str, delay: float = 0):
        self.message = message
        self.delay = delay

    def configure(self, config):
        pass

    def process(self, inputs):
        print(self.message, flush=True)
        if self.delay:
            time.sleep(self.delay)
        yield PipelineContext()


class ConsoleProbeSource(Step):
    def __init__(self, path: Path):
        self.path = path

    def configure(self, config):
        pass

    def process(self, inputs):
        import ctypes

        self.path.write_text(str(ctypes.windll.kernel32.GetConsoleWindow()), encoding="utf-8")
        print("console probe output", flush=True)
        yield PipelineContext()


class PrintingStep(Step):
    def __init__(self, message: str):
        self.message = message

    def configure(self, config):
        pass

    def process(self, inputs):
        for item in inputs:
            print(self.message, flush=True)
            yield item


class PausedSource(Step):
    def configure(self, config):
        pass

    def __init__(self, release_path: Path):
        self.release_path = release_path

    def process(self, inputs):
        yield PipelineContext(value=1)
        while not self.release_path.exists():
            time.sleep(0.01)
        yield PipelineContext(value=2)


class ValueRecorder(Step):
    def configure(self, config):
        pass

    def __init__(self, result_path: Path):
        self.result_path = result_path

    def process(self, inputs):
        for item in inputs:
            with self.result_path.open("a", encoding="utf-8") as result:
                result.write(f"{item.value}\n")
            yield item


class ConfigurableOffset(Step):
    def configure(self, config):
        self.offset = config.offset

    def process(self, inputs):
        for item in inputs:
            yield PipelineContext(value=item.value + self.offset)


class StatusSource(Step):
    def configure(self, config):
        pass

    def __init__(self, healthy: bool):
        self.healthy = healthy

    def process(self, inputs):
        if self.healthy:
            from pipeworks.embedded.stream_report import record_receive
            record_receive(True)
        time.sleep(1.3)
        yield PipelineContext()


class YoloSource(Step):
    def __init__(self, model_path: Path, result_path: Path):
        self.model_path = model_path
        self.result_path = result_path

    def configure(self, config):
        pass

    def process(self, inputs):
        from pipeworks.local_yolo import infer

        image = torch.full((96, 64), 128, dtype=torch.uint8, device="cuda")
        result = infer(self.model_path, image, None, 0.25, 0)
        self.result_path.write_text(f"{os.getpid()}:{result.orig_shape}", encoding="utf-8")
        yield PipelineContext()


def _run_forever(directory_name: str) -> None:
    directory = Path(directory_name)
    config = directory / "child.yml"
    config.write_text("{}", encoding="utf-8")
    Pipeline("child", config=config).step(RecordingSource(directory / "child.pid", continuous=True)).run()


def _run_print(directory_name: str, message: str, result) -> None:
    directory = Path(directory_name)
    config = directory / f"{message}.yml"
    config.write_text("{}", encoding="utf-8")
    output = StringIO()
    with redirect_stdout(output):
        Pipeline(message, config=config).step(PrintingSource(message)).run()
    result.put(output.getvalue())


def _run_tap_print(directory_name: str, message: str, result) -> None:
    directory = Path(directory_name)
    config = directory / f"sink-{message}.yml"
    config.write_text("{}", encoding="utf-8")
    output = StringIO()
    with redirect_stdout(output):
        Pipeline(message, config=config).step(PrintingSource("report output")).step(Tap(PrintingStep(message))).run()
    result.put(output.getvalue())


def _run_status_report(directory_name: str, healthy: bool, result) -> None:
    config = Path(directory_name) / f"status-{healthy}.yml"
    config.write_text("{}", encoding="utf-8")
    output = StringIO()
    with redirect_stdout(output):
        Pipeline(f"status-{healthy}", config=config).step(StatusSource(healthy)).step(StreamReport()).run()
    result.put((healthy, output.getvalue()))


class CentralProcessTests(unittest.TestCase):
    def test_development_constructor_contract(self):
        with TemporaryDirectory() as temporary:
            config = Path(temporary) / "config.yml"
            config.write_text("{}", encoding="utf-8")
            with patch("pipeworks.main._connect") as connect:
                for value in (None, 0, 1, "true", "development", [], {}):
                    with self.subTest(value=value), self.assertRaisesRegex(TypeError, "development"):
                        Pipeline("invalid", config=config, development=value)
                pipeline = Pipeline("default", config=config)
                self.assertIs(pipeline.development, False)
                with self.assertRaises(TypeError):
                    pipeline.run(server_group="development")
                connect.assert_not_called()
            for development in (False, True):
                pipeline = Pipeline("mode", config=config, development=development)
                restored = cloudpickle.loads(cloudpickle.dumps(pipeline))
                self.assertIs(restored.development, development)
                with patch("pipeworks.main.run_remote") as remote:
                    pipeline.run()
                    remote.assert_called_once_with(pipeline)
        self.assertEqual(_server_endpoint(), (_ADDRESS, _LOCK_PATH))
        self.assertEqual(_server_endpoint("production"), (_ADDRESS, _LOCK_PATH))
        self.assertNotEqual(_server_endpoint("development"), _server_endpoint("Development"))

    def test_concurrent_groups_reuse_only_their_own_server(self):
        with TemporaryDirectory() as temporary:
            directory = Path(temporary)
            groups = [False, True]
            failures = []

            def run(group, index):
                try:
                    self._pipeline(directory, f"{group}-{index}",
                                   RecordingSource(directory / f"{group}-{index}.pid"), development=group).run()
                except Exception as error:
                    failures.append(error)

            threads = [Thread(target=run, args=(group, index)) for group in groups for index in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=15)
                self.assertFalse(thread.is_alive())
            self.assertEqual(failures, [])
            pids = [[int((directory / f"{group}-{index}.pid").read_text(encoding="utf-8"))
                     for index in range(2)] for group in groups]
            self.assertEqual(pids[0][0], pids[0][1])
            self.assertEqual(pids[1][0], pids[1][1])
            self.assertNotEqual(pids[0][0], pids[1][0])
            self.assertNotIn(os.getpid(), pids[0] + pids[1])

    def _open_group_stream(self, directory, group):
        path = directory / f"{group}.pid"
        pipeline = self._pipeline(directory, group, ProgressSource(path, continuous=True))
        cloudpickle.register_pickle_by_value(sys.modules[__name__])
        _start_server(group)
        process = _launched_servers[-1]
        connection = _connect(group)
        connection.send_bytes(cloudpickle.dumps(pipeline))

        def heartbeat():
            while True:
                time.sleep(0.25)
                try:
                    connection.send_bytes(b"alive")
                except (EOFError, OSError):
                    return

        Thread(target=heartbeat, daemon=True).start()
        deadline = time.monotonic() + 10
        while not path.with_suffix(".progress").exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        if not path.with_suffix(".progress").exists():
            connection.close()
            self.fail("그룹 영상이 시작되지 않았습니다.")
        return connection, path, int(path.read_text(encoding="utf-8")), process

    def _assert_group_progress(self, group, path, pid):
        with _connect(group) as ping:
            ping.send_bytes(b"ping")
            self.assertEqual(ping.recv(), ("pong", pid))
        before = path.with_suffix(".progress").read_text(encoding="utf-8")
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            if path.with_suffix(".progress").read_text(encoding="utf-8") != before:
                break
            time.sleep(0.02)
        else:
            self.fail("운영 영상 처리가 계속되지 않았습니다.")
        self.assertFalse(path.with_suffix(".closed").exists())

    def test_development_crash_does_not_stop_production(self):
        with TemporaryDirectory() as temporary:
            directory = Path(temporary)
            production = f"test-production-{uuid.uuid4().hex}"
            development = f"test-development-{uuid.uuid4().hex}"
            prod, path, prod_pid, _ = self._open_group_stream(directory, production)
            dev = None
            try:
                dev, _, dev_pid, process = self._open_group_stream(directory, development)
                # Windows venv launchers can have a different PID from the Python server.
                os.kill(dev_pid, signal.SIGTERM)
                process.wait(timeout=5)
                self._assert_group_progress(production, path, prod_pid)
            finally:
                if dev is not None:
                    dev.close()
                prod.close()

    def test_development_idle_exit_and_restart_are_independent(self):
        with TemporaryDirectory() as temporary:
            directory = Path(temporary)
            production = f"test-production-{uuid.uuid4().hex}"
            development = f"test-development-{uuid.uuid4().hex}"
            prod, path, prod_pid, _ = self._open_group_stream(directory, production)
            dev = None
            try:
                dev, _, dev_pid, process = self._open_group_stream(directory, development)
                dev.close()
                dev = None
                deadline = time.monotonic() + 5
                while process.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.05)
                self.assertIsNotNone(process.poll())
                self._assert_group_progress(production, path, prod_pid)
                replacement_path = directory / "replacement.pid"
                replacement = self._pipeline(directory, "replacement", RecordingSource(replacement_path), development=True)
                # Use the isolated test server while exercising constructor-based routing.
                with patch("pipeworks.main._connect", side_effect=lambda group: _connect(development)):
                    with patch("pipeworks.main._start_server", side_effect=lambda group: _start_server(development)):
                        replacement.run()
                self.assertNotEqual(dev_pid, int(replacement_path.read_text(encoding="utf-8")))
                self._assert_group_progress(production, path, prod_pid)
            finally:
                if dev is not None:
                    dev.close()
                prod.close()

    def test_concurrent_stream_reports_keep_receive_status_separate(self):
        with TemporaryDirectory() as temporary:
            context = get_context("spawn")
            result = context.Queue()
            processes = [context.Process(target=_run_status_report, args=(temporary, healthy, result))
                         for healthy in (True, False)]
            for process in processes:
                process.start()
            try:
                outputs = dict(result.get(timeout=15) for _ in processes)
                self.assertIn("수신 성공", outputs[True])
                self.assertIn("수신 대기", outputs[False])
                self.assertNotIn("수신 성공", outputs[False])
            finally:
                for process in processes:
                    process.join(timeout=5)
                    if process.is_alive():
                        process.terminate()
                        process.join(timeout=5)
            self.assertTrue(all(process.exitcode == 0 for process in processes))

    def test_terminal_stream_report_reaches_caller_console(self):
        with TemporaryDirectory() as temporary:
            config = Path(temporary) / "report.yml"
            config.write_text("{}", encoding="utf-8")
            pipeline = (Pipeline("terminal-report", config=config)
                        .step(PrintingSource("source active", delay=1.3))
                        .step(StreamReport()))
            output = StringIO()
            with redirect_stdout(output):
                pipeline.run()
            self.assertIn("source active", output.getvalue())
            self.assertIn("수신 대기", output.getvalue())
            self.assertIn("송신 대기", output.getvalue())
            self.assertIn("FPS 0.0", output.getvalue())

    def test_running_central_pipeline_applies_config_file_change(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path = root / "config.yml"
            config_path.write_text("ConfigurableOffset:\n  offset: 10\n", encoding="utf-8")
            result_path = root / "result.txt"
            release_path = root / "release"
            pipeline = (Pipeline("central-config", config=config_path)
                        .step(PausedSource(release_path))
                        .step(ConfigurableOffset())
                        .step(ValueRecorder(result_path)))
            failures = []

            def run():
                try:
                    pipeline.run()
                except Exception as error:
                    failures.append(error)

            runner = Thread(target=run)
            runner.start()
            try:
                deadline = time.monotonic() + 10
                while (not result_path.exists() or not result_path.read_text(encoding="utf-8")) and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertTrue(result_path.exists())
                self.assertEqual(result_path.read_text(encoding="utf-8"), "11\n")
                config_path.write_text("ConfigurableOffset:\n  offset: 20\n", encoding="utf-8")
                time.sleep(0.6)
                release_path.touch()
                runner.join(timeout=10)
                self.assertFalse(runner.is_alive())
                self.assertEqual(failures, [])
                self.assertEqual(result_path.read_text(encoding="utf-8"), "11\n22\n")
            finally:
                release_path.touch()
                runner.join(timeout=5)

    def test_user_step_with_neighbor_import_hotswaps_in_central_process(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            helper_name = f"central_neighbor_{uuid.uuid4().hex}"
            (root / f"{helper_name}.py").write_text("OFFSET = 100\n", encoding="utf-8")
            step_path = root / "user_step.py"
            release_path = root / "release"
            result_path = root / "result.txt"
            config_path = root / "config.yml"
            config_path.write_text("{}", encoding="utf-8")

            def code(offset):
                return (
                    f"from {helper_name} import OFFSET\n"
                    "from pipeworks.models import Step, PipelineContext\n"
                    "class UserStep(Step):\n"
                    "    def configure(self, config):\n"
                    "        pass\n"
                    "    def process(self, inputs):\n"
                    "        for item in inputs:\n"
                    f"            yield PipelineContext(value=item.value + OFFSET + {offset})\n"
                )

            step_path.write_text(code(0), encoding="utf-8")
            module_name = f"central_user_step_{uuid.uuid4().hex}"
            module = types.ModuleType(module_name)
            module.__file__ = str(step_path)
            module.__package__ = ""
            sys.modules[module_name] = module
            sys.path.insert(0, str(root))
            try:
                exec(compile(step_path.read_text(encoding="utf-8"), str(step_path), "exec"), module.__dict__)
                user_step = module.UserStep()
            finally:
                sys.path.remove(str(root))
                sys.modules.pop(helper_name, None)

            pipeline = (Pipeline("central-hotswap", config=config_path)
                        .step(PausedSource(release_path))
                        .step(user_step)
                        .step(ValueRecorder(result_path)))
            sys.modules.pop(module_name, None)
            failures = []

            def run():
                try:
                    pipeline.run()
                except Exception as error:
                    failures.append(error)

            runner = Thread(target=run)
            runner.start()
            try:
                deadline = time.monotonic() + 10
                while (not result_path.exists() or not result_path.read_text(encoding="utf-8")) and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertTrue(result_path.exists())
                self.assertEqual(result_path.read_text(encoding="utf-8"), "101\n")
                step_path.write_text(code(1000), encoding="utf-8")
                time.sleep(0.6)
                release_path.touch()
                runner.join(timeout=10)
                self.assertFalse(runner.is_alive())
                self.assertEqual(failures, [])
                self.assertEqual(result_path.read_text(encoding="utf-8"), "101\n1102\n")
            finally:
                release_path.touch()
                runner.join(timeout=5)

    def test_server_has_no_console_window_and_forwards_output(self):
        with TemporaryDirectory() as temporary:
            directory = Path(temporary)
            path = directory / "console.txt"
            pipeline = self._pipeline(directory, "console", ConsoleProbeSource(path))
            output = StringIO()
            with redirect_stdout(output):
                pipeline.run()
            self.assertEqual(path.read_text(encoding="utf-8"), "0")
            self.assertEqual(output.getvalue(), "console probe output\n")

    def test_server_executable_falls_back_to_current_python(self):
        with patch("pipeworks.main.Path.is_file", return_value=False):
            self.assertEqual(_server_executable(), sys.executable)

    def test_tap_step_output_reaches_calling_stdout(self):
        with TemporaryDirectory() as temporary:
            config = Path(temporary) / "sink.yml"
            config.write_text("{}", encoding="utf-8")
            pipeline = Pipeline("sink", config=config).step(PrintingSource("report output")).step(Tap(PrintingStep("post output")))
            output = StringIO()
            with redirect_stdout(output):
                pipeline.run()
            self.assertIn("report output\n", output.getvalue())
            self.assertIn("post output\n", output.getvalue())

    def test_concurrent_tap_outputs_stay_with_their_callers(self):
        with TemporaryDirectory() as temporary:
            context = get_context("spawn")
            result = context.Queue()
            processes = [context.Process(target=_run_tap_print, args=(temporary, message, result))
                         for message in ("first sink", "second sink")]
            for process in processes:
                process.start()
            try:
                outputs = [result.get(timeout=15) for _ in processes]
                self.assertEqual(len(outputs), 2)
                self.assertTrue(all("report output\n" in output for output in outputs))
                self.assertEqual({output.replace("report output\n", "") for output in outputs},
                                 {"first sink\n", "second sink\n"})
            finally:
                for process in processes:
                    process.join(timeout=5)
                    if process.is_alive():
                        process.terminate()
                        process.join(timeout=5)
            self.assertTrue(all(process.exitcode == 0 for process in processes))

    def test_step_output_reaches_calling_stdout(self):
        with TemporaryDirectory() as temporary:
            pipeline = self._pipeline(Path(temporary), "print", PrintingSource("step output"))
            output = StringIO()
            with redirect_stdout(output):
                pipeline.run()
            self.assertEqual(output.getvalue(), "step output\n")

    def test_step_output_arrives_before_run_finishes(self):
        with TemporaryDirectory() as temporary:
            pipeline = self._pipeline(Path(temporary), "live", PrintingSource("live output", delay=1))
            output = StringIO()
            with redirect_stdout(output):
                runner = Thread(target=pipeline.run)
                runner.start()
                deadline = time.monotonic() + 5
                while "live output" not in output.getvalue() and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertIn("live output", output.getvalue())
                self.assertTrue(runner.is_alive())
                runner.join(timeout=5)
                self.assertFalse(runner.is_alive())

    def test_concurrent_callers_receive_only_their_own_output(self):
        with TemporaryDirectory() as temporary:
            context = get_context("spawn")
            result = context.Queue()
            processes = [context.Process(target=_run_print, args=(temporary, message, result))
                         for message in ("first", "second")]
            for process in processes:
                process.start()
            try:
                outputs = {result.get(timeout=15) for _ in processes}
                self.assertEqual(outputs, {"first\n", "second\n"})
            finally:
                for process in processes:
                    process.join(timeout=5)
                    if process.is_alive():
                        process.terminate()
                        process.join(timeout=5)
            self.assertTrue(all(process.exitcode == 0 for process in processes))

    def test_pipe_address_uses_windows_sid(self):
        import hashlib
        from pipeworks import main

        sid = _user_sid()
        expected = hashlib.sha256((str(Path(main.__file__).resolve().parent) + sid).encode()).hexdigest()[:20]
        self.assertEqual(_KEY, expected)
        self.assertIn(expected, _ADDRESS)

    def test_server_start_reports_original_error(self):
        class FailedProcess:
            stderr = BytesIO(b"PermissionError: [WinError 5] Access is denied\n")
            returncode = 1

            def poll(self):
                return 1

        with patch("pipeworks.main._connect", side_effect=OSError("unavailable")):
            with patch("pipeworks.main.subprocess.Popen", return_value=FailedProcess()):
                with self.assertRaisesRegex(RuntimeError, "WinError 5"):
                    _start_server()

    def _pipeline(self, directory: Path, name: str, source: Step, *, development=False) -> Pipeline:
        config = directory / f"{name}.yml"
        config.write_text("{}", encoding="utf-8")
        return Pipeline(name, config=config, development=development).step(source)

    def test_run_executes_in_shared_process(self):
        with TemporaryDirectory() as temporary:
            directory = Path(temporary)
            paths = [directory / "first.pid", directory / "second.pid"]
            pipelines = [self._pipeline(directory, str(index), RecordingSource(path)) for index, path in enumerate(paths)]
            threads = [Thread(target=pipelines[0].run),
                       Thread(target=pipelines[1].run)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)
                self.assertFalse(thread.is_alive())
            pids = [int(path.read_text(encoding="utf-8")) for path in paths]
            self.assertEqual(pids[0], pids[1])
            self.assertNotEqual(pids[0], os.getpid())

    def test_run_reports_failure(self):
        with TemporaryDirectory() as temporary:
            pipeline = self._pipeline(Path(temporary), "error", FailingSource())
            pipeline.steps = [FailingSource()]
            with self.assertRaisesRegex(RuntimeError, "expected failure"):
                pipeline.run()

    @unittest.skipUnless(torch.cuda.is_available(), "CUDA가 필요합니다")
    def test_gpu_inference_stays_in_central_process(self):
        model_path = Path(__file__).resolve().parents[1] / "examples" / "model" / "yolo11n.engine"
        if not model_path.is_file():
            self.skipTest("예제 모델이 필요합니다")
        with TemporaryDirectory() as temporary:
            directory = Path(temporary)
            result_path = directory / "result.txt"
            pipeline = self._pipeline(directory, "gpu", YoloSource(model_path, result_path))
            pipeline.run()
            pid, shape = result_path.read_text(encoding="utf-8").split(":", 1)
            self.assertNotEqual(int(pid), os.getpid())
            self.assertEqual(shape, "(64, 64)")

    def test_disconnected_client_stops_its_stream(self):
        with TemporaryDirectory() as temporary:
            directory = Path(temporary)
            path = directory / "continuous.pid"
            pipeline = self._pipeline(directory, "continuous", RecordingSource(path, continuous=True))
            other_path = directory / "other.pid"
            other = self._pipeline(directory, "other", RecordingSource(other_path, continuous=True))
            _start_server()
            connection = _connect()
            other_connection = _connect()
            cloudpickle.register_pickle_by_value(sys.modules[__name__])
            connection.send_bytes(cloudpickle.dumps(pipeline))
            other_connection.send_bytes(cloudpickle.dumps(other))
            deadline = time.monotonic() + 10
            while (not path.exists() or not other_path.exists()) and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertTrue(path.exists())
            self.assertTrue(other_path.exists())
            connection.close()
            while not path.with_suffix(".closed").exists() and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertTrue(path.with_suffix(".closed").exists())
            self.assertFalse(other_path.with_suffix(".closed").exists())
            other_connection.close()
            while not other_path.with_suffix(".closed").exists() and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertTrue(other_path.with_suffix(".closed").exists())

    def test_server_exits_after_last_pipeline_disconnects(self):
        with TemporaryDirectory() as temporary:
            directory = Path(temporary)
            cloudpickle.register_pickle_by_value(sys.modules[__name__])
            _start_server()
            connections = []
            try:
                for name in ("first", "second"):
                    connection = _connect()
                    connections.append(connection)
                    pipeline = self._pipeline(directory, name, RecordingSource(directory / f"{name}.pid", continuous=True))
                    connection.send_bytes(cloudpickle.dumps(pipeline))
                deadline = time.monotonic() + 10
                while not all((directory / f"{name}.pid").exists() for name in ("first", "second")) and time.monotonic() < deadline:
                    time.sleep(0.05)
                self.assertTrue(all((directory / f"{name}.pid").exists() for name in ("first", "second")))
                server_pid = int((directory / "first.pid").read_text(encoding="utf-8"))
                self.assertEqual(server_pid, int((directory / "second.pid").read_text(encoding="utf-8")))

                connections.pop(0).close()
                time.sleep(1.5)
                with _connect() as ping:
                    ping.send_bytes(b"ping")
                    self.assertEqual(ping.recv(), ("pong", server_pid))

                connections.pop().close()
                replacement = _connect()
                connections.append(replacement)
                replacement_pipeline = self._pipeline(directory, "replacement", RecordingSource(directory / "replacement.pid", continuous=True))
                replacement.send_bytes(cloudpickle.dumps(replacement_pipeline))
                deadline = time.monotonic() + 5
                while not (directory / "replacement.pid").exists() and time.monotonic() < deadline:
                    time.sleep(0.05)
                self.assertEqual(server_pid, int((directory / "replacement.pid").read_text(encoding="utf-8")))
                time.sleep(1.5)
                with _connect() as ping:
                    ping.send_bytes(b"ping")
                    self.assertEqual(ping.recv(), ("pong", server_pid))

                connections.pop().close()
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    try:
                        with _connect() as ping:
                            ping.send_bytes(b"ping")
                            ping.recv()
                    except (EOFError, OSError):
                        break
                    time.sleep(0.05)
                else:
                    self.fail("마지막 파이프라인 연결 후 중앙 프로세스가 종료되지 않았습니다.")
            finally:
                for connection in connections:
                    connection.close()

    def test_terminated_caller_stops_stream(self):
        with TemporaryDirectory() as temporary:
            directory = Path(temporary)
            process = get_context("spawn").Process(target=_run_forever, args=(temporary,))
            process.start()
            try:
                marker = directory / "child.pid"
                deadline = time.monotonic() + 10
                while not marker.exists() and time.monotonic() < deadline:
                    time.sleep(0.05)
                self.assertTrue(marker.exists())
                process.terminate()
                process.join(timeout=5)
                closed = marker.with_suffix(".closed")
                while not closed.exists() and time.monotonic() < deadline:
                    time.sleep(0.05)
                self.assertTrue(closed.exists())
            finally:
                if process.is_alive():
                    process.terminate()
                process.join(timeout=5)
