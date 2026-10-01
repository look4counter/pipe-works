"""RTSP 미디어 파이프라인 실행 인자와 검증 규칙."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class PipelineArguments:
    input_rtsp_url: str
    input_rtsp_transport: str
    output_rtsp_url: str
    output_rtsp_transport: str
    pipe_type: str
    gpu_id: int
    metadata_enabled: bool
    metadata_path: str | None
    inference_enabled: bool
    inference_path: str | None
    inference_interval: int
    inference_frame: str | None
    postprocess_enabled: bool
    postprocess_path: str | None
    process_id: str | None = None
    fps: int = 30
    log_level: str = "INFO"

    def __post_init__(self) -> None:
        if self.pipe_type == "bypass":
            object.__setattr__(self, "metadata_enabled", False)
            object.__setattr__(self, "inference_enabled", False)
            object.__setattr__(self, "postprocess_enabled", False)
        if self.inference_interval is None:
            object.__setattr__(self, "inference_interval", 3)
        if self.fps is None:
            object.__setattr__(self, "fps", 30)


def _boolean(value: str) -> bool:
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    raise argparse.ArgumentTypeError("값은 true 또는 false여야 합니다.")


def _positive_integer(value: str) -> int:
    try:
        number = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("값은 양의 정수여야 합니다.") from error
    if number < 1:
        raise argparse.ArgumentTypeError("값은 양의 정수여야 합니다.")
    return number


def _rtsp_url(value: str) -> str:
    if not value.startswith("rtsp://"):
        raise argparse.ArgumentTypeError("RTSP URL은 rtsp://로 시작해야 합니다.")
    return value


def _path_for_enabled_stage(enabled: bool, path: str | None, name: str) -> None:
    if enabled and not path:
        raise ValueError(f"{name}-enabled가 true이면 --{name}-path가 필요합니다.")
    if path is not None and not path.strip():
        raise ValueError(f"--{name}-path는 비어 있을 수 없습니다.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="RTSP 미디어 파이프라인 실행 설정을 검증합니다.")
    parser.add_argument("--input-rtsp-url", required=True, type=_rtsp_url)
    parser.add_argument("--input-rtsp-transport", required=True)
    parser.add_argument("--output-rtsp-url", required=True, type=_rtsp_url)
    parser.add_argument("--output-rtsp-transport", required=True)
    parser.add_argument("--pipe-type", required=True, choices=("nvidia", "bypass"))
    parser.add_argument("--gpuid", dest="gpu_id", type=int, default=0)
    parser.add_argument("--fps", type=_positive_integer, default=30)
    parser.add_argument("--metadata-enabled", required=True, type=_boolean)
    parser.add_argument("--metadata-path")
    parser.add_argument("--inference-enabled", required=True, type=_boolean)
    parser.add_argument("--inference-path")
    parser.add_argument("--inference-interval", type=_positive_integer, default=3)
    parser.add_argument("--inference-frame", choices=("pytorch",))
    parser.add_argument("--postprocess-enabled", required=True, type=_boolean)
    parser.add_argument("--postprocess-path")
    parser.add_argument("--process-id")
    parser.add_argument(
        "--log-level",
        type=str.upper,
        choices=("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"),
        default="INFO",
        help="Logging threshold (default: INFO)",
    )
    return parser


def parse_arguments(argv: Sequence[str] | None = None) -> PipelineArguments:
    namespace = build_parser().parse_args(argv)
    if namespace.pipe_type != "bypass":
        _path_for_enabled_stage(namespace.metadata_enabled, namespace.metadata_path, "metadata")
        _path_for_enabled_stage(namespace.inference_enabled, namespace.inference_path, "inference")
        _path_for_enabled_stage(namespace.postprocess_enabled, namespace.postprocess_path, "postprocess")
    else:
        namespace.metadata_enabled = False
        namespace.inference_enabled = False
        namespace.postprocess_enabled = False
    if namespace.pipe_type != "bypass" and namespace.inference_enabled and namespace.inference_frame is None:
        raise ValueError("inference-enabled가 true이면 --inference-frame이 필요합니다.")
    return PipelineArguments(**vars(namespace))
