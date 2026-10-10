"""파이프라인 실행별 프레임 처리 통계를 상세 형식으로 출력한다."""

import time
import sys
from contextlib import contextmanager
from contextvars import ContextVar, copy_context
from dataclasses import dataclass, field, replace
from threading import Event, Lock, Thread
from types import SimpleNamespace
from typing import Iterator

from pipeworks.models import PipelineContext, Step

@dataclass(frozen=True, slots=True)
class _Sample:
    at: float
    seconds: float
    previous: "_Sample | None"
    total: float
    count: int
    first_at: float


@dataclass(frozen=True, slots=True)
class _History:
    head: _Sample | None = None
    chunks: tuple[_Sample, ...] = ()

    def append(self, now: float, seconds: float) -> "_History":
        previous = self.head
        chunks = self.chunks
        if previous is not None and int(previous.at) != int(now):
            chunks = tuple(head for head in (previous, *chunks) if head.at > now - 10)
            previous = None
        head = _Sample(now, seconds, previous,
                       seconds + (previous.total if previous is not None else 0.0),
                       1 + (previous.count if previous is not None else 0),
                       previous.first_at if previous is not None else now)
        return _History(head, chunks)

    def average(self, now: float) -> float | None:
        total, count = 0.0, 0
        heads = (self.head, *self.chunks) if self.head is not None else self.chunks
        for head in heads:
            if head.at <= now - 10:
                break
            if head.first_at > now - 10 and head.at <= now:
                total += head.total
                count += head.count
                continue
            # Only the boundary chunk needs individual sample inspection.
            sample = head
            while sample is not None and sample.at > now - 10:
                if sample.at <= now:
                    total += sample.seconds
                    count += 1
                sample = sample.previous
        return total / count * 1000 if count else None


@dataclass(frozen=True, slots=True)
class _Snapshot:
    started_at: float | None = None
    completed_frames: int = 0
    processing_seconds: float = 0.0
    completed_inferences: int = 0
    inference_seconds: float = 0.0
    frame_history: _History = field(default_factory=_History)
    inference_history: _History = field(default_factory=_History)
    stages: tuple[tuple[str, int, float], ...] = ()
    receive_success_at: float | None = None
    receive_failure_at: float | None = None
    publish_success_at: float | None = None
    publish_failure_at: float | None = None


@dataclass
class _ReportStats:
    detection_stats: object | None = None
    lock: Lock = field(default_factory=Lock)
    snapshot: _Snapshot = field(default_factory=_Snapshot)


@dataclass(frozen=True, slots=True)
class _ReportView:
    metrics: tuple
    stages: tuple[tuple[str, float], ...]
    connections: tuple[str, str]


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
        snapshot = stats.snapshot
        stages = {name: (count, total) for name, count, total in snapshot.stages}
        count, total = stages.get(name, (0, 0.0))
        stages[name] = (count + 1, total + max(0.0, seconds))
        stats.snapshot = replace(snapshot, stages=tuple(
            (name, count, total) for name, (count, total) in stages.items()))


def record_receive(success: bool) -> None:
    stats = _stats()
    with stats.lock:
        now = time.perf_counter()
        if success:
            stats.snapshot = replace(stats.snapshot, receive_success_at=now)
        else:
            stats.snapshot = replace(stats.snapshot, receive_failure_at=now)


def record_publish(success: bool) -> None:
    stats = _stats()
    with stats.lock:
        now = time.perf_counter()
        if success:
            stats.snapshot = replace(stats.snapshot, publish_success_at=now)
        else:
            stats.snapshot = replace(stats.snapshot, publish_failure_at=now)


def _connection_status(now: float, snapshot: _Snapshot | None = None) -> tuple[str, str]:
    snapshot = _stats().snapshot if snapshot is None else snapshot

    def status(succeeded_at: float | None, failed_at: float | None) -> str:
        if failed_at is not None and (succeeded_at is None or failed_at >= succeeded_at):
            return "실패"
        if succeeded_at is None:
            return "대기"
        return "중단" if now - succeeded_at > 5.0 else "성공"

    return (
        status(snapshot.receive_success_at, snapshot.receive_failure_at),
        status(snapshot.publish_success_at, snapshot.publish_failure_at),
    )


def record_frame(processing_seconds: float) -> None:
    stats = _stats()
    with stats.lock:
        now = time.perf_counter()
        snapshot = stats.snapshot
        seconds = max(0.0, processing_seconds)
        stats.snapshot = replace(snapshot,
            started_at=now if snapshot.started_at is None else snapshot.started_at,
            completed_frames=snapshot.completed_frames + 1,
            processing_seconds=snapshot.processing_seconds + seconds,
            frame_history=snapshot.frame_history.append(now, seconds))


def record_inference(inference_seconds: float) -> None:
    stats = _stats()
    with stats.lock:
        now = time.perf_counter()
        snapshot = stats.snapshot
        seconds = max(0.0, inference_seconds)
        stats.snapshot = replace(snapshot,
            started_at=now if snapshot.started_at is None else snapshot.started_at,
            completed_inferences=snapshot.completed_inferences + 1,
            inference_seconds=snapshot.inference_seconds + seconds,
            inference_history=snapshot.inference_history.append(now, seconds))


class _ReportReader:
    """Observe one published snapshot without locking or changing collectors."""

    def __init__(self, stats: _ReportStats):
        self.stats = stats
        snapshot = stats.snapshot
        self.started_at = snapshot.started_at if snapshot.started_at is not None else time.perf_counter()
        self.previous = _Snapshot()

    def read(self, *, now: float | None = None) -> _ReportView | None:
        # CPython 3.11 publishes a single object reference. All reachable
        # statistics are immutable, so writers can replace it while we read.
        snapshot = self.stats.snapshot
        now = time.perf_counter() if now is None else now
        elapsed = now - self.started_at
        if elapsed < 1.0:
            return None
        previous = self.previous
        frames = snapshot.completed_frames - previous.completed_frames
        inferences = snapshot.completed_inferences - previous.completed_inferences
        old_stages = {name: (count, total) for name, count, total in previous.stages}
        stages = []
        for name, count, total in snapshot.stages:
            old_count, old_total = old_stages.get(name, (0, 0.0))
            if count > old_count:
                stages.append((name, (total - old_total) / (count - old_count) * 1000))
        view = _ReportView(
            (frames / elapsed,
             (snapshot.processing_seconds - previous.processing_seconds) / frames * 1000 if frames else 0.0,
             inferences,
             (snapshot.inference_seconds - previous.inference_seconds) / inferences * 1000 if inferences else None,
             snapshot.frame_history.average(now), snapshot.inference_history.average(now)),
            tuple(stages), _connection_status(now, snapshot),
        )
        self.previous = snapshot
        self.started_at = now
        return view


class StreamReport(Step):
    def configure(self, config: SimpleNamespace) -> None:
        pass

    def process(self, inputs: Iterator[PipelineContext]) -> Iterator[PipelineContext]:
        from pipeworks.main import _current_output_writer, _use_output_writer

        done = Event()
        output_writer = _current_output_writer()
        context = copy_context()
        reader = _ReportReader(_stats())

        def report_once() -> None:
            snapshot = reader.read()
            if snapshot is None:
                return
            fps, average_ms, inference_count, average_inference_ms, recent_frame_ms, recent_inference_ms = snapshot.metrics
            receive_status, publish_status = snapshot.connections
            recent_frame = "없음" if recent_frame_ms is None else f"{recent_frame_ms:.1f}ms"
            inference = "없음" if average_inference_ms is None else f"{average_inference_ms:.1f}ms"
            recent_inference = "없음" if recent_inference_ms is None else f"{recent_inference_ms:.1f}ms"
            parts = [
                f"수신 {receive_status}",
                f"송신 {publish_status}",
                f"FPS {fps:.1f}",
                f"프레임처리 {average_ms:.1f}ms/1s, {recent_frame}/10s",
                f"추론 {inference}/1s, {recent_inference}/10s"
                + (f" ({inference_count}건)" if inference_count else ""),
            ]
            stages = dict(snapshot.stages)
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
