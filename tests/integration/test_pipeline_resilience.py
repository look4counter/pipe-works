"""Opt-in GPU/RTSP test for long streams, input reconnect, and module reload."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

import av
import pytest


def _required_environment() -> tuple[str, str, str]:
    publish_url = os.getenv("PIPE_WORKS_TEST_PUBLISH_RTSP_URL")
    output_url = os.getenv("PIPE_WORKS_TEST_OUTPUT_RTSP_URL")
    ffmpeg = os.getenv("PIPE_WORKS_TEST_FFMPEG") or shutil.which("ffmpeg")
    if not publish_url or not output_url or not ffmpeg:
        pytest.skip(
            "Set PIPE_WORKS_TEST_PUBLISH_RTSP_URL and "
            "PIPE_WORKS_TEST_OUTPUT_RTSP_URL, and install FFmpeg"
        )
    return publish_url, output_url, ffmpeg


def _start_publisher(ffmpeg: str, publish_url: str, transport: str):
    return subprocess.Popen(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-re",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=640x360:rate=30",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-tune",
            "zerolatency",
            "-g",
            "30",
            "-f",
            "rtsp",
            "-rtsp_transport",
            transport,
            publish_url,
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _write_inference_module(path: Path, marker_path: Path, version: str) -> None:
    source = f'''from pathlib import Path

_frames = 0

def on_frame(infer, _parameters, frame):
    global _frames
    if not infer:
        return frame
    _frames += 1
    if _frames % 30 == 0:
        with Path({str(marker_path)!r}).open("a", encoding="utf-8") as marker:
            marker.write("{version}:{{}}\\n".format(_frames))
    return frame
'''
    temporary_path = path.with_suffix(".tmp")
    temporary_path.write_text(source, encoding="utf-8")
    temporary_path.replace(path)


def _wait_for_marker(
    marker_path: Path,
    version: str,
    process: subprocess.Popen,
    timeout_seconds: float,
    stderr_file,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            stderr_file.seek(0)
            details = stderr_file.read().decode("utf-8", errors="replace")
            pytest.fail(
                f"Pipeline exited with status {process.returncode}: {details}"
            )
        if marker_path.exists() and any(
            line.startswith(f"{version}:")
            for line in marker_path.read_text(encoding="utf-8").splitlines()
        ):
            return
        time.sleep(0.2)
    pytest.fail(f"Pipeline did not process module version {version!r}")


def _assert_output_packet(output_url: str, transport: str) -> None:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        output = None
        try:
            output = av.open(
                output_url,
                mode="r",
                options={"rtsp_transport": transport},
                timeout=(2.0, 2.0),
            )
            streams = output.streams.video
            if streams:
                for packet in output.demux(streams[0]):
                    if packet.size > 0:
                        return
        except av.error.FFmpegError:
            pass
        finally:
            if output is not None:
                output.close()
        time.sleep(0.5)
    pytest.fail("No video packet arrived from the RTSP output")


def test_long_stream_reconnect_and_live_module_reload(tmp_path: Path) -> None:
    publish_url, output_url, ffmpeg = _required_environment()
    input_transport = os.getenv("PIPE_WORKS_TEST_INPUT_RTSP_TRANSPORT", "tcp")
    output_transport = os.getenv("PIPE_WORKS_TEST_OUTPUT_RTSP_TRANSPORT", "tcp")
    gpu_id = os.getenv("PIPE_WORKS_TEST_GPU_ID", "0")
    long_stream_seconds = float(
        os.getenv("PIPE_WORKS_TEST_LONG_STREAM_SECONDS", "30")
    )
    reconnect_pause_seconds = float(
        os.getenv("PIPE_WORKS_TEST_RECONNECT_PAUSE_SECONDS", "8")
    )
    inference_path = tmp_path / "live_inference.py"
    marker_path = tmp_path / "callbacks.txt"
    _write_inference_module(inference_path, marker_path, "v1")

    command = [
        sys.executable,
        "-m",
        "pipeline.cli",
        "--input-rtsp-url",
        publish_url,
        "--input-rtsp-transport",
        input_transport,
        "--output-rtsp-url",
        output_url,
        "--output-rtsp-transport",
        output_transport,
        "--pipe-type",
        "nvidia",
        "--gpuid",
        gpu_id,
        "--fps",
        "30",
        "--metadata-enabled",
        "false",
        "--inference-enabled",
        "true",
        "--inference-path",
        str(inference_path),
        "--inference-interval",
        "1",
        "--inference-frame",
        "pytorch",
        "--postprocess-enabled",
        "false",
    ]

    publisher = None
    pipeline = None
    with tempfile.TemporaryFile(mode="w+b") as stderr_file:
        try:
            publisher = _start_publisher(ffmpeg, publish_url, input_transport)
            time.sleep(2)
            if publisher.poll() is not None:
                pytest.skip("FFmpeg could not publish to the configured RTSP path")

            pipeline = subprocess.Popen(
                command,
                cwd=Path(__file__).resolve().parents[2],
                stdout=subprocess.DEVNULL,
                stderr=stderr_file,
            )
            _wait_for_marker(marker_path, "v1", pipeline, 60, stderr_file)
            _assert_output_packet(output_url, output_transport)

            time.sleep(max(0, long_stream_seconds))
            _write_inference_module(inference_path, marker_path, "v2")
            _wait_for_marker(marker_path, "v2", pipeline, 30, stderr_file)

            publisher.terminate()
            publisher.wait(timeout=10)
            time.sleep(max(5, reconnect_pause_seconds))
            publisher = _start_publisher(ffmpeg, publish_url, input_transport)
            time.sleep(2)
            if publisher.poll() is not None:
                pytest.fail("FFmpeg could not republish after the RTSP interruption")

            _write_inference_module(inference_path, marker_path, "v3")
            _wait_for_marker(marker_path, "v3", pipeline, 60, stderr_file)
            _assert_output_packet(output_url, output_transport)
        finally:
            for child in (pipeline, publisher):
                if child is not None and child.poll() is None:
                    child.terminate()
                    try:
                        child.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        child.wait(timeout=5)
