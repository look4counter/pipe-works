"""파이프라인 실행별 프레임 처리 통계를 상세 형식으로 출력한다."""

import time
import sys
from contextlib import contextmanager
from contextvars import ContextVar, copy_context
from collections import deque
from dataclasses import dataclass, field
from threading import Event, Lock, Thread
from types import SimpleNamespace
from typing import Iterator

from pipeworks.models import PipelineContext, Step

@dataclass(frozen=True, slots=True)
class _History:
    samples: tuple[tuple[float, float], ...] = ()

    def average(self, now: float) -> float | None:
        total, count = 0.0, 0
        for at, seconds in self.samples:
            if now - 10 < at <= now:
                total += seconds
                count += 1
        return total / count * 1000 if count else None


@dataclass(frozen=True, slots=True)
class _Snapshot:
    published_at: float | None = None
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
    enabled: bool = True
    detection_stats: object | None = None
    lock: Lock = field(default_factory=Lock)
    snapshot: _Snapshot = field(default_factory=_Snapshot)
    started_at: float | None = None
    completed_frames: int = 0
    processing_seconds: float = 0.0
    completed_inferences: int = 0
    inference_seconds: float = 0.0
    frame_history: deque = field(default_factory=deque)
    inference_history: deque = field(default_factory=deque)
    stages: dict[str, list] = field(default_factory=dict)
    receive_success_at: float | None = None
    receive_failure_at: float | None = None
    publish_success_at: float | None = None
    publish_failure_at: float | None = None

    def publish(self, *, now: float | None = None) -> None:
        with self.lock:
            now = time.perf_counter() if now is None else now
            _prune(self.frame_history, now)
            _prune(self.inference_history, now)
            self.snapshot = _Snapshot(
                published_at=now, started_at=self.started_at,
                completed_frames=self.completed_frames, processing_seconds=self.processing_seconds,
                completed_inferences=self.completed_inferences, inference_seconds=self.inference_seconds,
                frame_history=_History(tuple(self.frame_history)),
                inference_history=_History(tuple(self.inference_history)),
                stages=tuple((name, values[0], values[1]) for name, values in self.stages.items()),
                receive_success_at=self.receive_success_at, receive_failure_at=self.receive_failure_at,
                publish_success_at=self.publish_success_at, publish_failure_at=self.publish_failure_at,
            )


def _prune(history: deque, now: float) -> None:
    while history and history[0][0] <= now - 10:
        history.popleft()


class _Publisher:
    def __init__(self):
        self.entries = {}
        self.stats = ()
        self.done = Event()
        self.thread = Thread(target=self.run, name="pipeworks-stats-publisher", daemon=True)

    def run(self):
        while not self.done.wait(.1):
            for stats in self.stats:
                stats.publish()


_publisher_lock = Lock()
_publisher = None


@contextmanager
def _publishing(stats):
    global _publisher
    with _publisher_lock:
        if _publisher is None:
            _publisher = _Publisher()
            _publisher.thread.start()
        publisher = _publisher
        key = id(stats)
        _, count, enabled = publisher.entries.get(key, (stats, 0, stats.enabled))
        stats.enabled = True
        publisher.entries[key] = (stats, count + 1, enabled)
        publisher.stats = tuple(entry[0] for entry in publisher.entries.values())
    try:
        yield
    finally:
        stopping = False
        with _publisher_lock:
            _, count, enabled = publisher.entries[key]
            if count == 1:
                del publisher.entries[key]
                stats.enabled = enabled
            else:
                publisher.entries[key] = (stats, count - 1, enabled)
            publisher.stats = tuple(entry[0] for entry in publisher.entries.values())
            if not publisher.entries:
                publisher.done.set()
                _publisher = None
                stopping = True
        if stopping:
            publisher.thread.join()


@dataclass(frozen=True, slots=True)
class _ReportView:
    metrics: tuple
    stages: tuple[tuple[str, float], ...]
    connections: tuple[str, str]


_default_stats = _ReportStats(enabled=False)
_current_stats: ContextVar[_ReportStats | None] = ContextVar("pipeworks_report_stats", default=None)


def _stats() -> _ReportStats:
    return _current_stats.get() or _default_stats


@contextmanager
def report_scope(*, enabled: bool = True):
    token = _current_stats.set(_ReportStats(enabled=enabled))
    try:
        yield
    finally:
        _current_stats.reset(token)


def record_stage(name: str, seconds: float) -> None:
    stats = _stats()
    if not stats.enabled:
        return
    with stats.lock:
        values = stats.stages.get(name)
        if values is None:
            values = stats.stages[name] = [0, 0.0]
        values[0] += 1
        values[1] += max(0.0, seconds)


def record_receive(success: bool) -> None:
    stats = _stats()
    if not stats.enabled:
        return
    with stats.lock:
        now = time.perf_counter()
        if success:
            stats.receive_success_at = now
        else:
            stats.receive_failure_at = now


def record_publish(success: bool) -> None:
    stats = _stats()
    if not stats.enabled:
        return
    with stats.lock:
        now = time.perf_counter()
        if success:
            stats.publish_success_at = now
        else:
            stats.publish_failure_at = now


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
    if not stats.enabled:
        return
    with stats.lock:
        now = time.perf_counter()
        seconds = max(0.0, processing_seconds)
        if stats.started_at is None:
            stats.started_at = now
        stats.completed_frames += 1
        stats.processing_seconds += seconds
        stats.frame_history.append((now, seconds))
        _prune(stats.frame_history, now)


def record_inference(inference_seconds: float) -> None:
    stats = _stats()
    if not stats.enabled:
        return
    with stats.lock:
        now = time.perf_counter()
        seconds = max(0.0, inference_seconds)
        if stats.started_at is None:
            stats.started_at = now
        stats.completed_inferences += 1
        stats.inference_seconds += seconds
        stats.inference_history.append((now, seconds))
        _prune(stats.inference_history, now)


class _ReportReader:
    """Observe one published snapshot without locking or changing collectors."""

    def __init__(self, stats: _ReportStats):
        self.stats = stats
        snapshot = stats.snapshot
        self.started_at = snapshot.started_at if snapshot.started_at is not None else time.perf_counter()
        self.previous = _Snapshot()
        self.observed_at = self.started_at

    def read(self, *, now: float | None = None) -> _ReportView | None:
        # CPython 3.11 publishes a single object reference. All reachable
        # statistics are immutable, so writers can replace it while we read.
        snapshot = self.stats.snapshot
        now = time.perf_counter() if now is None else now
        elapsed = now - self.started_at
        if elapsed < 1.0:
            return None
        published_at = snapshot.published_at if snapshot.published_at is not None else now
        elapsed = max(0.0, published_at - self.observed_at)
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
            (frames / elapsed if elapsed else 0.0,
             (snapshot.processing_seconds - previous.processing_seconds) / frames * 1000 if frames else 0.0,
             inferences,
             (snapshot.inference_seconds - previous.inference_seconds) / inferences * 1000 if inferences else None,
             snapshot.frame_history.average(now), snapshot.inference_history.average(now)),
            tuple(stages), _connection_status(now, snapshot),
        )
        self.previous = snapshot
        self.started_at = now
        self.observed_at = published_at
        return view


class StreamReport(Step):
    def configure(self, config: SimpleNamespace) -> None:
        pass

    def process(self, inputs: Iterator[PipelineContext]) -> Iterator[PipelineContext]:
        with _publishing(_stats()):
            yield from self._process(inputs)

    def _process(self, inputs: Iterator[PipelineContext]) -> Iterator[PipelineContext]:
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
