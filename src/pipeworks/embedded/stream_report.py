"""파이프라인 실행별 프레임 처리 통계를 상세 형식으로 출력한다."""

import time
import sys
from contextlib import contextmanager
from contextvars import ContextVar, copy_context
from dataclasses import dataclass, field
from threading import Event, Lock, Thread
from types import SimpleNamespace
from typing import Iterator

from pipeworks.models import PipelineContext, Step

@dataclass
class _ReportStats:
    lock: Lock = field(default_factory=Lock)
    window_started_at: float | None = None
    completed_frames: int = 0
    processing_seconds: float = 0.0
    completed_inferences: int = 0
    inference_seconds: float = 0.0
    stage_totals: dict[str, tuple[int, float]] = field(default_factory=dict)
    receive_success_at: float | None = None
    receive_failure_at: float | None = None
    publish_success_at: float | None = None
    publish_failure_at: float | None = None


_default_stats = _ReportStats()
_current_stats: ContextVar[_ReportStats | None] = ContextVar("pipeworks_report_stats", default=None)


def _stats() -> _ReportStats:
    return _current_stats.get() or _default_stats


@contextmanager
def report_scope():
    token = _current_stats.set(_ReportStats())
    try:
        yield
    finally:
        _current_stats.reset(token)


def record_stage(name: str, seconds: float) -> None:
    stats = _stats()
    with stats.lock:
        count, total = stats.stage_totals.get(name, (0, 0.0))
        stats.stage_totals[name] = (count + 1, total + max(0.0, seconds))


def record_receive(success: bool) -> None:
    stats = _stats()
    now = time.perf_counter()
    with stats.lock:
        if success:
            stats.receive_success_at = now
        else:
            stats.receive_failure_at = now


def record_publish(success: bool) -> None:
    stats = _stats()
    now = time.perf_counter()
    with stats.lock:
        if success:
            stats.publish_success_at = now
        else:
            stats.publish_failure_at = now


def _connection_status(now: float) -> tuple[str, str]:
    stats = _stats()

    def status(succeeded_at: float | None, failed_at: float | None) -> str:
        if failed_at is not None and (succeeded_at is None or failed_at >= succeeded_at):
            return "실패"
        if succeeded_at is None:
            return "대기"
        return "중단" if now - succeeded_at > 5.0 else "성공"

    with stats.lock:
        return (
            status(stats.receive_success_at, stats.receive_failure_at),
            status(stats.publish_success_at, stats.publish_failure_at),
        )


def _take_stage_report() -> dict[str, float]:
    stats = _stats()
    with stats.lock:
        averages = {name: total / count * 1000 for name, (count, total) in stats.stage_totals.items()}
        stats.stage_totals = {}
        return averages


def record_frame(processing_seconds: float) -> None:
    stats = _stats()
    now = time.perf_counter()
    with stats.lock:
        if stats.window_started_at is None:
            stats.window_started_at = now
        stats.completed_frames += 1
        stats.processing_seconds += max(0.0, processing_seconds)


def record_inference(inference_seconds: float) -> None:
    stats = _stats()
    now = time.perf_counter()
    with stats.lock:
        if stats.window_started_at is None:
            stats.window_started_at = now
        stats.completed_inferences += 1
        stats.inference_seconds += max(0.0, inference_seconds)


def _take_report() -> tuple[float, float, int, float | None] | None:
    stats = _stats()
    now = time.perf_counter()
    with stats.lock:
        if stats.window_started_at is None or now - stats.window_started_at < 1.0:
            return None
        fps = stats.completed_frames / (now - stats.window_started_at)
        average_ms = (
            stats.processing_seconds / stats.completed_frames * 1000 if stats.completed_frames else 0.0
        )
        inference_count = stats.completed_inferences
        average_inference_ms = (
            stats.inference_seconds / inference_count * 1000 if inference_count else None
        )
        stats.window_started_at = now
        stats.completed_frames = 0
        stats.processing_seconds = 0.0
        stats.completed_inferences = 0
        stats.inference_seconds = 0.0
        return (
            fps,
            average_ms,
            inference_count,
            average_inference_ms,
        )


class StreamReport(Step):
    def configure(self, config: SimpleNamespace) -> None:
        pass

    def process(self, inputs: Iterator[PipelineContext]) -> Iterator[PipelineContext]:
        from pipeworks.main import _current_output_writer, _use_output_writer

        done = Event()
        output_writer = _current_output_writer()
        context = copy_context()
        stats = _stats()
        with stats.lock:
            if stats.window_started_at is None:
                stats.window_started_at = time.perf_counter()

        def report_once() -> None:
            snapshot = _take_report() or (0.0, 0.0, 0, None)
            fps, average_ms, inference_count, average_inference_ms = snapshot
            receive_status, publish_status = _connection_status(time.perf_counter())
            parts = [
                f"수신 {receive_status}",
                f"송신 {publish_status}",
                f"FPS {fps:.1f}",
                f"프레임 처리 시간 {average_ms:.1f}ms",
            ]
            if average_inference_ms is None:
                parts.append("추론 없음")
            else:
                parts.append(f"추론 {average_inference_ms:.1f}ms ({inference_count}건)")
            stages = _take_stage_report()
            labels = (
                ("batch_queue", "입력 대기"),
                ("batch_wait", "배치 대기"),
                ("encode", "인코딩"),
                ("publish", "송출"),
            )
            detail = " | ".join(
                f"{label} {stages[name]:.1f}ms" for name, label in labels if name in stages
            )
            sys.stdout.write(" | ".join(parts) + "\n" + detail + "\n")
            sys.stdout.flush()

        def worker() -> None:
            with _use_output_writer(output_writer):
                while not done.wait(1.0):
                    context.run(report_once)

        thread = Thread(target=worker, name="pipeworks-stream-report", daemon=True)
        thread.start()
        try:
            yield from inputs
        finally:
            done.set()
            thread.join()
