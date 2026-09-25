import os
from unittest.mock import patch

import pytest
import psutil

from conductor.domain.supervisor import ProcessLookupError, Supervisor


def process_definition() -> dict[str, object]:
    return {
        "process_id": "camera-001", "input_rtsp_url": "rtsp://in",
        "input_rtsp_transport": "tcp", "output_rtsp_url": "rtsp://out",
        "output_rtsp_transport": "udp", "pipe_type": "nvidia", "gpu_id": 0,
        "metadata_enabled": False, "metadata_path": None,
        "inference_enabled": False, "inference_path": None,
        "inference_interval": None, "inference_frame": None,
        "postprocess_enabled": False, "postprocess_path": None,
    }


def test_start_process_passes_process_id_to_pipeline() -> None:
    process = process_definition()
    with patch("conductor.domain.supervisor.subprocess.Popen") as popen, patch.object(
        Supervisor, "_find_process_pid", return_value=None
    ):
        popen.return_value.pid = 1234
        popen.return_value.poll.return_value = None
        assert Supervisor().start_process(process) == 1234
        command = popen.call_args.args[0]
        assert command[command.index("--process-id") + 1] == "camera-001"
        assert command[command.index("--gpuid") + 1] == "0"


def test_start_process_passes_fps_and_optional_stage_arguments() -> None:
    process = process_definition()
    process.update({
        "fps": 24,
        "metadata_enabled": True,
        "metadata_path": "metadata.py",
        "inference_enabled": True,
        "inference_path": "inference.py",
        "inference_interval": 5,
        "inference_frame": "pytorch",
        "postprocess_enabled": False,
    })
    with patch("conductor.domain.supervisor.subprocess.Popen") as popen, patch.object(
        Supervisor, "_find_process_pid", return_value=None
    ):
        popen.return_value.pid = 1234
        Supervisor().start_process(process)

    command = popen.call_args.args[0]
    for option, expected in (
        ("--fps", "24"),
        ("--metadata-path", "metadata.py"),
        ("--inference-interval", "5"),
        ("--inference-frame", "pytorch"),
    ):
        assert command[command.index(option) + 1] == expected


def test_start_process_rejects_duplicate_process_id() -> None:
    process = process_definition()
    with patch.object(Supervisor, "_find_process_pid", return_value=1234), patch(
        "conductor.domain.supervisor.subprocess.Popen"
    ) as popen:
        with pytest.raises(ValueError, match="camera-001"):
            Supervisor().start_process(process)
        popen.assert_not_called()


@pytest.mark.skipif(os.name != "nt", reason="Windows command line parsing")
def test_windows_arguments_preserves_quoted_executable_path() -> None:
    arguments = Supervisor._windows_arguments(
        '"C:\\Program Files\\Python\\python.exe" -m pipeline.cli '
        '--process-id "camera 001"'
    )

    assert arguments == [
        "C:\\Program Files\\Python\\python.exe",
        "-m",
        "pipeline.cli",
        "--process-id",
        "camera 001",
    ]


def test_start_process_propagates_process_creation_error() -> None:
    process = process_definition()
    with patch.object(Supervisor, "_find_process_pid", return_value=None), patch(
        "conductor.domain.supervisor.subprocess.Popen",
        side_effect=OSError("python executable missing"),
    ):
        with pytest.raises(OSError, match="python executable missing"):
            Supervisor().start_process(process)


def test_stop_process_returns_false_when_taskkill_fails() -> None:
    with patch.object(Supervisor, "_find_process_pid", return_value=1234), patch(
        "conductor.domain.supervisor.subprocess.run"
    ) as run:
        run.return_value.returncode = 1
        assert Supervisor().stop_process("camera-001") is False


def test_stop_process_terminates_matched_windows_process() -> None:
    supervisor = Supervisor()
    with patch.object(
        Supervisor, "_find_process_pid", return_value=1234
    ), patch("conductor.domain.supervisor.subprocess.run") as run:
        run.return_value.returncode = 0
        assert supervisor.stop_process("camera-001") is True
        run.assert_called_once_with(
            ["taskkill", "/PID", "1234", "/T", "/F"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )


def test_pipeline_process_match_requires_exact_process_id() -> None:
    arguments = [
        "python.exe", "-m", "pipeline.cli", "--process-id", "camera-001"
    ]
    assert Supervisor._is_pipeline_process(arguments, "camera-001") is True
    assert Supervisor._is_pipeline_process(arguments, "camera-001-extra") is False


def test_process_state_lookup_reports_access_denied(monkeypatch) -> None:
    monkeypatch.setattr(
        "conductor.domain.supervisor.psutil.process_iter",
        lambda **_kwargs: (_ for _ in ()).throw(psutil.AccessDenied(pid=42)),
    )

    with pytest.raises(ProcessLookupError, match="denied access"):
        Supervisor().get_process_states(["camera-001"])
