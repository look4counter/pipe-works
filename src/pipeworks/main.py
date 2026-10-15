"""Run all requested pipelines in one local process."""

import hashlib
import csv
from collections import deque
from contextlib import contextmanager
from io import StringIO
import logging
import os
import re
from multiprocessing.connection import Client, Listener
from pathlib import Path
import subprocess
import sys
import tempfile
from threading import Event, Lock, Thread, Timer, local
import time
import uuid

import cloudpickle


logger = logging.getLogger(__name__)
_PROTOCOL = "central-v20"
_IDLE_SHUTDOWN = b"idle-shutdown"
_IDLE_SECONDS = 1.0


_output_lock = Lock()


class _ThreadOutput:
    def __init__(self, fallback):
        self.fallback = fallback
        self.current = local()

    def write(self, value):
        target = getattr(self.current, "write", self.fallback.write)
        return target(value)

    def flush(self):
        writer = getattr(self.current, "write", None)
        if writer is None:
            self.fallback.flush()
        elif callable(getattr(writer, "flush", None)):
            writer.flush()

    def __getattr__(self, name):
        return getattr(self.fallback, name)


def _install_output() -> _ThreadOutput:
    with _output_lock:
        if not isinstance(sys.stdout, _ThreadOutput):
            sys.stdout = _ThreadOutput(sys.stdout)
        return sys.stdout


def _current_output_writer():
    current = getattr(sys.stdout, "current", None)
    return getattr(current, "write", None)


@contextmanager
def _use_output_writer(writer):
    if writer is None:
        yield
        return
    from pipeworks.remote_logging import current_route, use_route

    output = sys.stdout
    missing = object()
    previous = getattr(output.current, "write", missing)
    output.current.write = writer
    with use_route(getattr(writer, "route", current_route())):
        try:
            yield
        finally:
            try:
                flush = getattr(writer, "flush", None)
                if callable(flush):
                    flush()
            finally:
                if previous is missing:
                    del output.current.write
                else:
                    output.current.write = previous


def _user_sid() -> str:
    output = subprocess.check_output(
        ["whoami", "/user", "/fo", "csv", "/nh"],
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    rows = list(csv.reader(StringIO(output)))
    if len(rows) != 1 or len(rows[0]) != 2 or not rows[0][1].startswith("S-1-"):
        raise RuntimeError("Windows 사용자 SID를 확인할 수 없습니다.")
    return rows[0][1]


_KEY = hashlib.sha256(
    (str(Path(__file__).resolve().parent) + _user_sid()).encode()
).hexdigest()[:20]
_ADDRESS = rf"\\.\pipe\pipeworks-{_PROTOCOL}-{_KEY}"
_LOCK_PATH = Path(tempfile.gettempdir()) / f"pipeworks-{_PROTOCOL}-{_KEY}.lock"
_launched_servers: list[subprocess.Popen] = []


def _server_endpoint(server_group="production"):
    if not isinstance(server_group, str):
        raise TypeError("server_group은 문자열이어야 합니다.")
    if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", server_group) is None:
        raise ValueError(
            "server_group은 영문자·숫자·밑줄·하이픈으로 이루어진 1~64자여야 합니다."
        )
    if server_group == "production":
        return _ADDRESS, _LOCK_PATH
    group_key = hashlib.sha256(server_group.encode("utf-8")).hexdigest()
    return (
        f"{_ADDRESS}-{group_key}",
        _LOCK_PATH.with_name(f"{_LOCK_PATH.stem}-{group_key}.lock"),
    )


def _connect(server_group="production"):
    address, _ = _server_endpoint(server_group)
    return Client(address, family="AF_PIPE")


def _server_executable() -> str:
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    return str(pythonw) if pythonw.is_file() else sys.executable


def _start_server(server_group="production") -> None:
    import msvcrt

    _, lock_path = _server_endpoint(server_group)
    with lock_path.open("a+b") as lock:
        lock.seek(0)
        while True:
            try:
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                time.sleep(0.05)
        try:
            try:
                with _connect(server_group) as connection:
                    connection.send_bytes(b"ping")
                    if connection.recv()[0] == "pong":
                        return
            except (OSError, EOFError):
                pass

            flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
            errors: deque[str] = deque(maxlen=25)
            process = subprocess.Popen(
                [
                    _server_executable(),
                    "-m",
                    "pipeworks.main",
                    "--server-group",
                    server_group,
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                creationflags=flags,
                close_fds=True,
            )
            _launched_servers[:] = [
                item for item in _launched_servers if item.poll() is None
            ]
            _launched_servers.append(process)

            def collect_errors() -> None:
                assert process.stderr is not None
                for line in process.stderr:
                    errors.append(line.decode("utf-8", errors="replace").rstrip())

            Thread(target=collect_errors, daemon=True).start()
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                try:
                    with _connect(server_group) as connection:
                        connection.send_bytes(b"ping")
                        response = connection.recv()
                    if response[0] == "pong":
                        return
                except (OSError, EOFError):
                    if process.poll() is not None:
                        time.sleep(0.05)
                        detail = "\n".join(errors) or f"종료 코드 {process.returncode}"
                        raise RuntimeError(
                            f"중앙 스트림 프로세스가 시작 중 종료되었습니다:\n{detail}"
                        )
                    time.sleep(0.05)
            raise TimeoutError("중앙 스트림 프로세스 시작 시간이 초과되었습니다.")
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)


def run_remote(pipeline) -> None:
    server_group = "development" if pipeline.development else "production"
    try:
        from pipeworks.hotswap import Hotswap
        from pipeworks.embedded.tap_skip_if_busy import TapSkipIfBusy
        from pipeworks.embedded import CudaAsync, EveryNFrames

        def register_step(step) -> None:
            if isinstance(step, Hotswap):
                register_step(step.wrapped_step)
            if isinstance(step, TapSkipIfBusy):
                register_step(step.step)
            if isinstance(step, (CudaAsync, EveryNFrames)):
                for inner in step.steps:
                    register_step(inner)
            module_names = {type(step).__module__}
            # Reused methods can belong to a different user module than the Step.
            for cls in type(step).__mro__:
                for member in vars(cls).values():
                    member = getattr(member, "__func__", member)
                    module_name = getattr(member, "__module__", None)
                    if module_name is not None:
                        module_names.add(module_name)
            for module_name in module_names:
                if not module_name.startswith("pipeworks.") and module_name in sys.modules:
                    if module_name == type(step).__module__ or any(
                        module_name == cls.__module__.split(".")[0]
                        or module_name.startswith(cls.__module__.split(".")[0] + ".")
                        for cls in type(step).__mro__
                        if not cls.__module__.startswith("pipeworks.")
                        and cls.__module__ != "builtins"
                    ):
                        cloudpickle.register_pickle_by_value(sys.modules[module_name])

        for step in pipeline.steps:
            register_step(step)
        from pipeworks.remote_logging import capture_settings

        payload = cloudpickle.dumps({
            "pipeline": pipeline,
            "logging": capture_settings(),
            "execution_id": uuid.uuid4().hex,
        })
    except Exception as error:
        raise TypeError("파이프라인을 중앙 프로세스에 전달할 수 없습니다.") from error

    try:
        connection = _connect(server_group)
    except (OSError, EOFError):
        _start_server(server_group)
        connection = _connect(server_group)
    try:
        connection.send_bytes(payload)
        heartbeat_stop = Event()

        def heartbeat() -> None:
            while not heartbeat_stop.wait(0.25):
                try:
                    connection.send_bytes(b"alive")
                except (EOFError, OSError):
                    return

        sender = Thread(target=heartbeat, daemon=True)
        sender.start()
        while True:
            status, message = connection.recv()
            if status == "log":
                from pipeworks.remote_logging import dispatch_record

                dispatch_record(message)
                continue
            break
    except (EOFError, OSError) as error:
        raise RuntimeError("중앙 스트림 프로세스와의 연결이 끊겼습니다.") from error
    finally:
        if "heartbeat_stop" in locals():
            heartbeat_stop.set()
        connection.close()
    if status == "error":
        raise RuntimeError(message)
    if status != "ok":
        raise RuntimeError("중앙 스트림 프로세스가 잘못된 응답을 보냈습니다.")


def _handle(connection, payload: bytes | None = None) -> None:
    with connection:
        send_lock = Lock()

        def send(response) -> None:
            with send_lock:
                connection.send(response)

        try:
            if payload is None:
                payload = connection.recv_bytes()
            if payload == b"ping":
                connection.send(("pong", os.getpid()))
                return
            request = cloudpickle.loads(payload)
            pipeline = request["pipeline"]
            settings = request["logging"]
            execution_id = request["execution_id"]
            from pipeworks.pipeline import Pipeline

            if not isinstance(pipeline, Pipeline):
                raise TypeError("파이프라인 요청이 아닙니다.")
        except Exception as error:
            try:
                connection.send(("error", f"{type(error).__name__}: {error}"))
            except OSError:
                pass
            return

        stop = Event()
        finished = Event()

        def execute() -> None:
            from pipeworks.remote_logging import LogRoute, PrintAdapter, install_relay

            _install_output()
            install_relay(settings)
            route = LogRoute(send, stop, settings, pipeline.name, execution_id)
            writer = PrintAdapter(route)
            with _use_output_writer(writer):
                try:
                    pipeline._run_local(stop)
                    response = ("ok", None)
                except Exception as error:
                    logger.exception("파이프라인 실행 실패: %s", pipeline.name)
                    response = ("error", f"{type(error).__name__}: {error}")
                finally:
                    writer.close()
                    route.close()
            try:
                send(response)
            except (EOFError, OSError):
                pass
            finally:
                finished.set()

        Thread(target=execute, name=f"pipeworks-{pipeline.name}", daemon=True).start()
        last_seen = time.monotonic()
        while not finished.is_set():
            try:
                if connection.poll(0.1):
                    connection.recv_bytes()
                    last_seen = time.monotonic()
            except (EOFError, OSError):
                stop.set()
                break
            if time.monotonic() - last_seen > 2:
                stop.set()
                break
        if stop.is_set():
            finished.wait(10)


def serve(*, server_group="production") -> None:
    address, _ = _server_endpoint(server_group)
    try:
        with _connect(server_group) as connection:
            connection.send_bytes(b"ping")
            if connection.recv()[0] == "pong":
                logger.warning("중앙 스트림 프로세스가 이미 실행 중입니다.")
                return
    except (OSError, EOFError):
        pass

    active_connections = 0
    idle_generation = 0
    clients_lock = Lock()
    idle_timer: Timer | None = None

    def schedule_idle_shutdown() -> None:
        nonlocal idle_timer, idle_generation
        idle_generation += 1
        generation = idle_generation

        def wake_listener() -> None:
            with clients_lock:
                if active_connections or idle_generation != generation:
                    return
            try:
                with _connect(server_group) as wake:
                    wake.send_bytes(_IDLE_SHUTDOWN + generation.to_bytes(8, "big"))
            except (EOFError, OSError):
                pass

        idle_timer = Timer(_IDLE_SECONDS, wake_listener)
        idle_timer.daemon = True
        idle_timer.start()

    def handle_client(connection, payload: bytes) -> None:
        nonlocal active_connections
        try:
            _handle(connection, payload)
        finally:
            with clients_lock:
                active_connections -= 1
                if active_connections == 0:
                    schedule_idle_shutdown()

    with Listener(address, family="AF_PIPE") as listener:
        with clients_lock:
            schedule_idle_shutdown()
        try:
            while True:
                connection = listener.accept()
                try:
                    payload = connection.recv_bytes()
                except (EOFError, OSError):
                    connection.close()
                    continue
                if payload == b"ping":
                    try:
                        connection.send(("pong", os.getpid()))
                    except (EOFError, OSError):
                        pass
                    finally:
                        connection.close()
                    continue
                if (
                    payload.startswith(_IDLE_SHUTDOWN)
                    and len(payload) == len(_IDLE_SHUTDOWN) + 8
                ):
                    connection.close()
                    with clients_lock:
                        if (
                            active_connections == 0
                            and idle_generation == int.from_bytes(payload[-8:], "big")
                        ):
                            break
                    continue
                with clients_lock:
                    active_connections += 1
                    idle_generation += 1
                    if idle_timer is not None:
                        idle_timer.cancel()
                        idle_timer = None
                Thread(
                    target=handle_client, args=(connection, payload), daemon=True
                ).start()
        finally:
            with clients_lock:
                if idle_timer is not None:
                    idle_timer.cancel()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="중앙 스트림 프로세스를 실행합니다.")
    parser.add_argument(
        "--server-group",
        default="production",
        help="중앙 프로세스 그룹 (기본: production)",
    )
    serve(server_group=parser.parse_args().server_group)
