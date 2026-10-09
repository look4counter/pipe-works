"""감지 요청의 CPU/GPU 구간을 추가 동기화 없이 수집한다."""

from collections import Counter, deque
from contextlib import contextmanager
from contextvars import ContextVar, copy_context
from dataclasses import dataclass, field
from threading import Event, Lock, Thread
import sys
import time

import torch

from pipeworks.models import Step


_current = ContextVar("pipeworks_detection_profile", default=None)
LABELS = {
    "preprocess": "전처리", "queue": "배치 큐 대기", "input_wait": "입력 동기화",
    "input_copy": "입력 결합", "prepare": "모델 준비", "inference": "모델 실행",
    "postprocess": "후처리", "output_copy": "출력 복사",
    "completion_wait": "GPU 완료 대기", "other": "기타 실행 비용",
    "total": "전체",
}
STATES = {"completed": "완료", "skipped": "간격 건너뜀", "busy": "작업자 바쁨",
          "timeout": "타임아웃", "error": "오류", "partial": "부분 종료"}


@dataclass
class Sample:
    seconds: float = 0.0
    events: list = field(default_factory=list)
    gpu_ms: float | None = None

    def resolve(self):
        if self.events and all(end.query() for _, end in self.events):
            self.gpu_ms = sum(start.elapsed_time(end) for start, end in self.events)
            self.events.clear()


class DetectionStats:
    def __init__(self):
        self.lock = Lock()
        self.active = Counter()
        self.samples = {}
        self.states = {}

    def activate(self, kind, delta=1):
        with self.lock:
            self.active[kind] += delta

    def enabled(self, kind):
        with self.lock:
            return self.active[kind] > 0

    def _prune(self, records, now):
        while records and records[0][0] <= now - 10:
            records.popleft()

    def record(self, kind, samples, status):
        now = time.perf_counter()
        with self.lock:
            records = self.samples.setdefault(kind, deque(maxlen=10000))
            self._prune(records, now)
            records.append((now, samples))
            self._status(kind, status, now)

    def _status(self, kind, status, now):
        records = self.states.setdefault(kind, deque(maxlen=10000))
        self._prune(records, now)
        records.append((now, status))

    def status(self, kind, status):
        if self.enabled(kind):
            with self.lock:
                self._status(kind, status, time.perf_counter())

    def snapshot(self, kind, since):
        now = time.perf_counter()
        with self.lock:
            records = self.samples.setdefault(kind, deque(maxlen=10000))
            states = self.states.setdefault(kind, deque(maxlen=10000))
            self._prune(records, now)
            self._prune(states, now)
            for _, parts in records:
                for sample in parts.values():
                    sample.resolve()

            def averages(window):
                groups = {}
                for at, parts in records:
                    if at > window:
                        for name, sample in parts.items():
                            groups.setdefault(name, []).append(sample)
                result = {}
                for name, samples in groups.items():
                    gpu = [s.gpu_ms for s in samples if s.gpu_ms is not None]
                    result[name] = (sum(s.seconds for s in samples) * 1000 / len(samples),
                                    len(samples), sum(gpu) / len(gpu) if gpu else None, len(gpu))
                return result

            return {"window": averages(since), "recent": averages(now - 10),
                    "states": Counter(s for at, s in states if at > since),
                    "recent_states": Counter(s for _, s in states)}


def store():
    from pipeworks.embedded.stream_report import _stats
    stats = _stats()
    with stats.lock:
        if stats.detection_stats is None:
            stats.detection_stats = DetectionStats()
        return stats.detection_stats


class Profile:
    def __init__(self, kind, stats=None):
        self.kind, self.stats = kind, stats
        self.started = time.perf_counter()
        self.parts = {}
        self.finished = False

    def add(self, name, seconds, events=None):
        sample = self.parts.setdefault(name, Sample())
        sample.seconds += max(0.0, seconds)
        if events is not None:
            sample.events.append(events)

    def merge(self, other):
        for name, source in other.parts.items():
            sample = self.parts.setdefault(name, Sample())
            sample.seconds += source.seconds
            sample.events.extend(source.events)

    def finish(self, status="completed"):
        if self.finished:
            return
        self.finished = True
        total = time.perf_counter() - self.started
        self.add("other", max(0.0, total - sum(s.seconds for s in self.parts.values())))
        self.add("total", total)
        if self.stats is not None:
            # 리포트 스레드가 읽는 표본은 이후 단계의 수정과 분리한다.
            samples = {name: Sample(s.seconds, list(s.events), s.gpu_ms) for name, s in self.parts.items()}
            self.stats.record(self.kind, samples, status)


def begin(kind):
    stats = store()
    return Profile(kind, stats) if stats.enabled(kind) else None


def status(kind, state):
    store().status(kind, state)


@contextmanager
def use(profile):
    token = _current.set(profile)
    try:
        yield profile
    finally:
        _current.reset(token)


@contextmanager
def span(name, stream=None):
    profile = _current.get()
    if profile is None:
        yield
        return
    started = time.perf_counter()
    events = None
    if stream is not None:
        events = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
        events[0].record(stream)
    try:
        yield
    finally:
        if events is not None:
            events[1].record(stream)
        profile.add(name, time.perf_counter() - started, events)


class DetectionReport(Step):
    kind = ""

    def _write(self, stats, since):
        snapshot = stats.snapshot(self.kind, since)
        counts = " | ".join(f"{label} {snapshot['states'][name]}/{snapshot['recent_states'][name]}"
                            for name, label in STATES.items())
        lines = [f"{type(self).__name__} | 건수 1s/10s | {counts}"]

        def format_value(row):
            if row is None:
                return "없음"
            cpu, count, gpu, gpu_count = row
            gpu_text = "없음" if gpu is None else f"{gpu:.2f}ms(n={gpu_count})"
            return f"CPU {cpu:.2f}ms(n={count}), GPU {gpu_text}"

        for name, label in LABELS.items():
            lines.append(f"  {label}: {format_value(snapshot['window'].get(name))}/1s | "
                         f"{format_value(snapshot['recent'].get(name))}/10s")
        sys.stdout.write("\n".join(lines) + "\n")
        sys.stdout.flush()

    def process(self, inputs):
        from pipeworks.main import _current_output_writer, _use_output_writer
        stats = store()
        stats.activate(self.kind)
        done = Event()
        context = copy_context()
        output_writer = _current_output_writer()
        last = [time.perf_counter()]

        def report():
            now = time.perf_counter()
            self._write(stats, last[0])
            last[0] = now

        def worker():
            with _use_output_writer(output_writer):
                while not done.wait(1):
                    context.run(report)

        thread = Thread(target=worker, name=f"pipeworks-{self.kind}-report", daemon=True)
        thread.start()
        try:
            yield from inputs
        finally:
            done.set()
            thread.join()
            # 짧은 실행도 마지막 표본을 볼 수 있게 남은 구간을 출력한다.
            try:
                report()
            finally:
                stats.activate(self.kind, -1)
