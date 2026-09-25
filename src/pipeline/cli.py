"""RTSP 미디어 파이프라인 실행 파라미터를 검증한다."""

import logging
from collections.abc import Iterable, Iterator
from threading import Event, Thread
from typing import Sequence

import torch
import importlib.util
from pathlib import Path
from types import ModuleType

from pipeline.arguments import PipelineArguments, parse_arguments
from pipeline.receive import receive
from pipeline.nvidia_pipe.decode import nvidia_decode
from pipeline.nvidia_pipe.encode import nvidia_encode
from pipeline.send import send, send_bypass
from pipeline.context import FrameContext
from pipeline.statistics import PIPELINE_STATISTICS
from pipeline.stats_reporter import report_statistics
from pipeline.log_reporter import start_log_reporting, stop_log_reporting

logger = logging.getLogger(__name__)
MODULE_WATCH_INTERVAL_SECONDS = 1.0


def load_module(path: str | Path) -> ModuleType:
    path = Path(path).resolve()
    importlib.invalidate_caches()
    revision = path.stat().st_mtime_ns
    spec = importlib.util.spec_from_file_location(
        f"{path.stem}_{revision}",
        path,
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"모듈을 불러올 수 없습니다: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_stage_module(path: str | Path, stage: str) -> object:
    module = load_module(path)
    if stage == "metadata":
        return module.metadata()
    return module


def watch_module(
    path: str | Path,
    stage: str,
    module_state: dict[str, object],
    stop_event: Event,
    last_modified: int,
) -> None:
    """Replace a stage's loaded value when its source file changes."""
    module_path = Path(path).resolve()

    while not stop_event.wait(MODULE_WATCH_INTERVAL_SECONDS):
        try:
            modified = module_path.stat().st_mtime_ns
            if modified == last_modified:
                continue

            updated_module = load_stage_module(module_path, stage)
            module_state[stage] = updated_module
            last_modified = modified
            logger.info("Reloaded %s module from %s", stage, module_path)
        except Exception:
            # Keep using the previous value and retry on the next poll. This
            # handles editors that write a file in multiple steps.
            logger.exception("Could not reload %s module from %s", stage, module_path)


def attach_metadata(
    frames: Iterable[FrameContext], module_state: dict[str, object]
) -> Iterator[FrameContext]:
    """Attach the latest watched metadata value to each frame context."""
    for frame in frames:
        frame.metadata = module_state.get("metadata")
        yield frame


def run_inference(
    parameters: PipelineArguments,
    frames: Iterable[FrameContext],
    module_state: dict[str, object],
) -> Iterator[FrameContext]:
    """Call the inference hook on every frame, indicating whether to infer."""
    for frame_index, frame in enumerate(frames):
        inference_module = module_state.get("inference")
        if not isinstance(inference_module, ModuleType):
            raise RuntimeError("Enabled inference module is unavailable")
        infer = frame_index % parameters.inference_interval == 0
        try:
            with torch.cuda.stream(frame.cuda_stream):
                result = inference_module.on_frame(infer, parameters, frame)
        except Exception:
            PIPELINE_STATISTICS.increment("inferenceFailed")
            logger.exception("Inference on_frame 실패. 원본 프레임을 전달합니다.")
            yield frame
            continue
        yield result


def run_postprocess(
    parameters: PipelineArguments,
    frames: Iterable[FrameContext],
    module_state: dict[str, object],
) -> Iterator[FrameContext]:
    for frame in frames:
        postprocess_module = module_state.get("postprocess")
        if not isinstance(postprocess_module, ModuleType):
            logger.error("활성화된 postprocess 모듈을 사용할 수 없습니다. 원본 프레임을 전달합니다.")
            yield frame
            continue
        try:
            result = postprocess_module.on_frame(parameters, frame)
        except Exception:
            PIPELINE_STATISTICS.increment("postprocessFailed")
            logger.exception("Postprocess on_frame 실패. 원본 프레임을 전달합니다.")
            yield frame
            continue
        yield result


def main(argv: Sequence[str] | None = None, stop_event: Event | None = None) -> None:
    """실행 인자를 파싱하고 RTSP 수신을 수행한다."""

    parameters = parse_arguments(argv)
    _configure_logging(parameters.log_level)
    PIPELINE_STATISTICS.reset()
    log_reporting = (
        start_log_reporting(parameters.process_id)
        if parameters.process_id
        else None
    )
    try:
        _run_pipeline(parameters, stop_event)
    finally:
        if log_reporting is not None:
            stop_log_reporting(*log_reporting)


def _configure_logging(level: str) -> None:
    numeric_level = getattr(logging, level)
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s [%(name)s][%(levelname)s] %(message)s",
    )
    logging.getLogger().setLevel(numeric_level)
    # websockets logs every sent frame at DEBUG, including the full JSON log event.
    logging.getLogger("websockets.client").setLevel(logging.WARNING)


def _run_pipeline(
    parameters: PipelineArguments, stop_event: Event | None
) -> None:
    module_state: dict[str, object] = {}
    watched_stages = (
        ("metadata", parameters.metadata_enabled, parameters.metadata_path),
        ("inference", parameters.inference_enabled, parameters.inference_path),
        ("postprocess", parameters.postprocess_enabled, parameters.postprocess_path),
    )
    module_stop = Event()
    statistics_stop = Event()
    module_threads: list[Thread] = []
    active_stages: list[tuple[str, Path, int]] = []

    for stage, enabled, path in watched_stages:
        if not enabled:
            continue
        if path is None:
            raise ValueError(f"{stage}가 활성화됐지만 경로가 없습니다.")

        resolved_path = Path(path).resolve()
        last_modified = resolved_path.stat().st_mtime_ns
        try:
            module_state[stage] = load_stage_module(path, stage)
        except Exception:
            if stage != "metadata":
                raise
            # Metadata is optional per frame. Start the pipeline without it and
            # let the watcher retry loading the module in the background.
            logger.exception("Metadata 초기 로드 실패. metadata 없이 파이프를 시작합니다.")

        active_stages.append((stage, resolved_path, last_modified))

    for stage, path, last_modified in active_stages:
        thread = Thread(
            target=watch_module,
            args=(path, stage, module_state, module_stop, last_modified),
            name=f"{stage}-watcher",
            daemon=True,
        )
        thread.start()
        module_threads.append(thread)

    statistics_thread = None
    if parameters.process_id:
        statistics_thread = Thread(
            target=report_statistics,
            args=(parameters.process_id, statistics_stop),
            name="statistics-reporter",
            daemon=True,
        )
        statistics_thread.start()

    try:
        received_packets = receive(parameters, stop_event)
        if parameters.pipe_type == "bypass":
            send_bypass(parameters, received_packets)
            return

        decoded_frames = nvidia_decode(parameters, received_packets)

        if parameters.metadata_enabled:
            decoded_frames = attach_metadata(decoded_frames, module_state)

        if parameters.inference_enabled:
            inferenced_frames = run_inference(parameters, decoded_frames, module_state)
        else:
            inferenced_frames = decoded_frames

        if parameters.postprocess_enabled:
            postprocessed_frames = run_postprocess(
                parameters, inferenced_frames, module_state
            )
        else:
            postprocessed_frames = inferenced_frames

        encoded_frames = nvidia_encode(parameters, postprocessed_frames)
        send(parameters, encoded_frames)
    finally:
        module_stop.set()
        statistics_stop.set()
        for thread in module_threads:
            thread.join(timeout=MODULE_WATCH_INTERVAL_SECONDS + 1)
        if statistics_thread is not None:
            statistics_thread.join(timeout=0.2)


if __name__ == "__main__":
    main()
