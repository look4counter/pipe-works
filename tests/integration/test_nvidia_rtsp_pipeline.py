"""Opt-in end-to-end check for a configured NVIDIA and RTSP environment."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

import av
import pytest

from conductor.domain.supervisor import Supervisor
from conductor.repository.database import Database


def _load_configuration() -> dict[str, object]:
    input_url = os.getenv("PIPE_WORKS_TEST_INPUT_RTSP_URL")
    output_url = os.getenv("PIPE_WORKS_TEST_OUTPUT_RTSP_URL")
    if input_url and output_url:
        return {
            "input_rtsp_url": input_url,
            "output_rtsp_url": output_url,
            "input_rtsp_transport": os.getenv("PIPE_WORKS_TEST_INPUT_RTSP_TRANSPORT", "tcp"),
            "output_rtsp_transport": os.getenv("PIPE_WORKS_TEST_OUTPUT_RTSP_TRANSPORT", "tcp"),
            "gpu_id": int(os.getenv("PIPE_WORKS_TEST_GPU_ID", "0")),
            "fps": 30,
        }

    configured_db_path = os.getenv("PIPE_WORKS_DB_PATH")
    db_path = (
        Path(configured_db_path)
        if configured_db_path
        else Path(__file__).resolve().parents[2] / "pipe-works.db"
    )
    if not db_path.is_file():
        pytest.skip("No RTSP environment variables or local process database is configured")

    records = Database(db_path).list_processes()
    process_id = os.getenv("PIPE_WORKS_TEST_PROCESS_ID")
    if process_id:
        record = next((row for row in records if row["process_id"] == process_id), None)
        if record is None:
            pytest.skip("PIPE_WORKS_TEST_PROCESS_ID is not present in the process database")
    elif len(records) == 1:
        record = records[0]
    else:
        pytest.skip(
            "Set PIPE_WORKS_TEST_PROCESS_ID when the database has zero or multiple processes"
        )

    if Supervisor().is_process_running(str(record["process_id"])):
        pytest.skip("The configured pipeline process is already running")
    return record


def test_nvidia_rtsp_input_to_output_round_trip() -> None:
    config = _load_configuration()
    command = [
        sys.executable,
        "-m",
        "pipeline.cli",
        "--input-rtsp-url",
        str(config["input_rtsp_url"]),
        "--input-rtsp-transport",
        str(config["input_rtsp_transport"]),
        "--output-rtsp-url",
        str(config["output_rtsp_url"]),
        "--output-rtsp-transport",
        str(config["output_rtsp_transport"]),
        "--pipe-type",
        "nvidia",
        "--gpuid",
        str(config.get("gpu_id", 0)),
        "--fps",
        str(config.get("fps", 30)),
        "--metadata-enabled",
        "false",
        "--inference-enabled",
        "false",
        "--postprocess-enabled",
        "false",
    ]

    with tempfile.TemporaryFile(mode="w+b") as stderr_file:
        process = subprocess.Popen(
            command,
            cwd=Path(__file__).resolve().parents[2],
            stdout=subprocess.DEVNULL,
            stderr=stderr_file,
        )
        try:
            deadline = time.monotonic() + 60
            received_output_packet = False
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    stderr_file.seek(0)
                    details = stderr_file.read().decode("utf-8", errors="replace")
                    details = details.replace(str(config["input_rtsp_url"]), "<input RTSP URL>")
                    details = details.replace(str(config["output_rtsp_url"]), "<output RTSP URL>")
                    pytest.fail(
                        f"Pipeline exited with status {process.returncode}: {details}"
                    )

                output = None
                try:
                    output = av.open(
                        str(config["output_rtsp_url"]),
                        mode="r",
                        options={
                            "rtsp_transport": os.getenv(
                                "PIPE_WORKS_TEST_OUTPUT_RTSP_TRANSPORT",
                                str(config["output_rtsp_transport"]),
                            )
                        },
                        timeout=(3.0, 3.0),
                    )
                    streams = output.streams.video
                    if streams:
                        for packet in output.demux(streams[0]):
                            if packet.size > 0:
                                received_output_packet = True
                                break
                except av.error.FFmpegError:
                    pass
                finally:
                    if output is not None:
                        output.close()

                if received_output_packet:
                    break
                time.sleep(0.5)

            assert received_output_packet, "No encoded video packet arrived at the RTSP output"
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
