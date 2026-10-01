"""Windows OS 프로세스 목록에서 process_id로 파이프라인을 관리한다."""

from __future__ import annotations

import ctypes
import logging
import os
import subprocess
import sys
import threading
from typing import TYPE_CHECKING, Iterable, Mapping

import psutil

if TYPE_CHECKING:
    from conductor.repository.database import Database

logger = logging.getLogger(__name__)
_ACCESS_DENIED = object()


class ProcessLookupError(RuntimeError):
    """The OS did not provide enough information to determine process state."""


class Supervisor:
    def __init__(self, conductor_port: int = 8000) -> None:
        self._conductor_port = conductor_port
        self._monitor_stop = threading.Event()
        self._monitor_thread: threading.Thread | None = None
        self._lifecycle_lock = threading.RLock()
        self._user_started: set[str] = set()

    def start_process(
        self,
        process: Mapping[str, object],
        *,
        track_for_restart: bool = True,
    ) -> int:
        process_id = self._required_string(process, "process_id")
        with self._lifecycle_lock:
            if self._find_process_pid(process_id) is not None:
                raise ValueError(f"이미 실행 중인 process_id입니다: {process_id}")
            pid = subprocess.Popen(
                self._build_command(process),
                env={
                    **os.environ,
                    "PIPE_WORKS_CONDUCTOR_PORT": str(self._conductor_port),
                },
            ).pid
            if track_for_restart:
                self._user_started.add(process_id)
            return pid

    def start_auto_start_monitor(
        self, database: Database, interval_seconds: float = 1.0
    ) -> None:
        """사용자가 시작한 프로세스의 자동 재시작을 감시한다."""
        with self._lifecycle_lock:
            if self._monitor_thread is not None and self._monitor_thread.is_alive():
                return
            self._monitor_stop.clear()
            self._monitor_thread = threading.Thread(
                target=self._monitor_auto_start,
                args=(database, interval_seconds),
                name="conductor-auto-start",
                daemon=True,
            )
            self._monitor_thread.start()

    def stop_auto_start_monitor(self) -> None:
        with self._lifecycle_lock:
            thread = self._monitor_thread
            if thread is None:
                return
            self._monitor_stop.set()
        thread.join(timeout=5)
        with self._lifecycle_lock:
            if self._monitor_thread is thread and not thread.is_alive():
                self._monitor_thread = None

    def _monitor_auto_start(
        self, database: Database, interval_seconds: float
    ) -> None:
        while not self._monitor_stop.is_set():
            with self._lifecycle_lock:
                tracked_process_ids = set(self._user_started)

            if not tracked_process_ids:
                self._monitor_stop.wait(max(interval_seconds, 0.01))
                continue

            try:
                processes = {
                    str(process["process_id"]): process
                    for process in database.list_processes()
                    if str(process["process_id"]) in tracked_process_ids
                }
                for process_id in tracked_process_ids - processes.keys():
                    with self._lifecycle_lock:
                        self._user_started.discard(process_id)
                enabled_processes = {
                    process_id: process
                    for process_id, process in processes.items()
                    if bool(process.get("auto_start"))
                }
                process_pids = self._find_pipeline_processes(
                    set(enabled_processes)
                )
                for process_id in tracked_process_ids:
                    process = enabled_processes.get(process_id)
                    if process is None:
                        # Unchecking auto_start disables restart only; it must not
                        # terminate a process that is already running.
                        continue
                    try:
                        with self._lifecycle_lock:
                            if (
                                process_id in self._user_started
                                and process_id not in process_pids
                            ):
                                self.start_process(process, track_for_restart=False)
                    except Exception:
                        logger.exception("auto_start 조정 실패: %s", process_id)
            except Exception:
                logger.exception("auto_start 설정 조회 실패")
            self._monitor_stop.wait(max(interval_seconds, 0.01))

    def is_process_running(self, process_id: str) -> bool:
        return self._find_process_pid(process_id) is not None

    def get_process_states(
        self, process_ids: Iterable[str]
    ) -> dict[str, bool | None]:
        requested = set(process_ids)
        running_ids = self._find_pipeline_processes(requested)
        return {process_id: process_id in running_ids for process_id in requested}

    def stop_process(self, process_id: str) -> bool:
        """명령행의 --process-id가 일치하는 Windows 프로세스를 종료한다."""

        with self._lifecycle_lock:
            self._user_started.discard(process_id)
            pid = self._find_process_pid(process_id)
            if pid is None:
                return False
            result = subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            return result.returncode == 0

    def _find_process_pid(self, process_id: str) -> int | None:
        return self._find_pipeline_processes({process_id}).get(process_id)

    @classmethod
    def _find_pipeline_processes(cls, process_ids: set[str]) -> dict[str, int]:
        if not process_ids:
            return {}
        matches: dict[str, int] = {}
        try:
            processes = psutil.process_iter(
                attrs=["pid", "name", "cmdline"], ad_value=_ACCESS_DENIED
            )
            for process in processes:
                try:
                    info = process.info
                    name = info.get("name")
                    if name is _ACCESS_DENIED:
                        raise ProcessLookupError(
                            "OS denied access to a process name during enumeration"
                        )
                    if not isinstance(name, str) or name.casefold() not in {
                        "python.exe",
                        "pythonw.exe",
                    }:
                        continue
                    arguments = info.get("cmdline")
                    if arguments is _ACCESS_DENIED:
                        raise ProcessLookupError(
                            "OS denied access to a Python process command line"
                        )
                    if not isinstance(arguments, list):
                        continue
                    process_id = cls._pipeline_process_id(arguments)
                    if process_id in process_ids:
                        matches[process_id] = int(info["pid"])
                        if len(matches) == len(process_ids):
                            break
                except (psutil.NoSuchProcess, psutil.ZombieProcess):
                    continue
                except (psutil.AccessDenied, OSError) as error:
                    raise ProcessLookupError(
                        "OS denied access while inspecting a process"
                    ) from error
        except (psutil.AccessDenied, OSError) as error:
            raise ProcessLookupError(
                "OS denied access while enumerating processes"
            ) from error
        except psutil.Error as error:
            raise ProcessLookupError(
                "OS process enumeration failed"
            ) from error
        return matches

    @staticmethod
    def _pipeline_process_id(arguments: list[str]) -> str | None:
        if "-m" not in arguments or "pipeline.cli" not in arguments:
            return None
        try:
            option_index = arguments.index("--process-id")
        except ValueError:
            return None
        value = arguments[option_index + 1 : option_index + 2]
        return value[0] if value else None

    @staticmethod
    def _windows_arguments(command_line: str) -> list[str]:
        argument_count = ctypes.c_int()
        command_line_to_argv = ctypes.windll.shell32.CommandLineToArgvW
        command_line_to_argv.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_int)]
        command_line_to_argv.restype = ctypes.POINTER(ctypes.c_wchar_p)
        arguments = command_line_to_argv(command_line, ctypes.byref(argument_count))
        if not arguments:
            return []
        try:
            return [arguments[index] for index in range(argument_count.value)]
        finally:
            local_free = ctypes.windll.kernel32.LocalFree
            local_free.argtypes = [ctypes.c_void_p]
            local_free.restype = ctypes.c_void_p
            local_free(arguments)

    @staticmethod
    def _is_pipeline_process(arguments: list[str], process_id: str) -> bool:
        return (
            "-m" in arguments
            and "pipeline.cli" in arguments
            and "--process-id" in arguments
            and arguments[arguments.index("--process-id") + 1 : arguments.index("--process-id") + 2]
            == [process_id]
        )

    def _build_command(self, process: Mapping[str, object]) -> list[str]:
        process_id = self._required_string(process, "process_id")
        command = [sys.executable, "-m", "pipeline.cli", "--process-id", process_id]
        for field in (
            "input_rtsp_url", "input_rtsp_transport", "output_rtsp_url",
            "output_rtsp_transport", "pipe_type", "metadata_enabled",
            "inference_enabled", "postprocess_enabled",
        ):
            command.extend((f"--{field.replace('_', '-')}", self._argument_value(process[field])))
        for field in (
            "gpu_id", "fps", "metadata_path", "inference_path", "inference_interval",
            "inference_frame", "postprocess_path", "log_level",
        ):
            value = process.get(field)
            if value is not None:
                option = "--gpuid" if field == "gpu_id" else f"--{field.replace('_', '-')}"
                command.extend((option, self._argument_value(value)))
        return command

    @staticmethod
    def _required_string(process: Mapping[str, object], field: str) -> str:
        value = process.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field}는 비어 있지 않은 문자열이어야 합니다.")
        return value

    @staticmethod
    def _argument_value(value: object) -> str:
        return str(value).lower() if isinstance(value, bool) else str(value)
