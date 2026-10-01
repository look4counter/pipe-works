"""Realtime runtime policies used behind the Pipeline DSL."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum
from time import monotonic

from pipeworks.models import Frame, PipelineContext


class DropPolicy(str, Enum):
    DROP_OLDEST = "drop_oldest"
    DROP_NEWEST = "drop_newest"
    BLOCK = "block"
    LATEST = "latest"


@dataclass(frozen=True)
class QueueMetrics:
    depth: int
    dropped_count: int
    max_depth_seen: int


class FrameQueue:
    """Bounded frame queue for real-time video freshness."""

    def __init__(
        self,
        max_frames: int,
        drop_policy: DropPolicy | str = DropPolicy.DROP_OLDEST,
    ) -> None:
        if max_frames <= 0:
            raise ValueError("max_frames must be greater than zero")
        self.max_frames = max_frames
        self.drop_policy = DropPolicy(drop_policy)
        if self.drop_policy == DropPolicy.LATEST:
            self.drop_policy = DropPolicy.DROP_OLDEST
        self._frames: deque[Frame] = deque()
        self._dropped_count = 0
        self._max_depth_seen = 0

    def put(self, frame: Frame) -> bool:
        """Insert a frame.

        Returns True when the incoming frame is retained. Returns False when the
        incoming frame is dropped or when block policy refuses immediate insert.
        """

        if len(self._frames) < self.max_frames:
            self._frames.append(frame)
            self._record_depth()
            return True

        if self.drop_policy == DropPolicy.DROP_OLDEST:
            self._frames.popleft()
            self._frames.append(frame)
            self._dropped_count += 1
            self._record_depth()
            return True

        if self.drop_policy == DropPolicy.DROP_NEWEST:
            self._dropped_count += 1
            return False

        if self.drop_policy == DropPolicy.BLOCK:
            return False

        raise ValueError(f"unsupported drop policy {self.drop_policy}")

    def get(self) -> Frame | None:
        if not self._frames:
            return None
        return self._frames.popleft()

    def latest(self) -> Frame | None:
        if not self._frames:
            return None
        return self._frames[-1]

    def drain_latest(self) -> Frame | None:
        frame = self.latest()
        self._frames.clear()
        return frame

    def drain_all(self) -> list[Frame]:
        frames = list(self._frames)
        self._frames.clear()
        return frames

    @property
    def metrics(self) -> QueueMetrics:
        return QueueMetrics(
            depth=len(self._frames),
            dropped_count=self._dropped_count,
            max_depth_seen=self._max_depth_seen,
        )

    def _record_depth(self) -> None:
        self._max_depth_seen = max(self._max_depth_seen, len(self._frames))


class ContextQueue:
    """Bounded handoff queue between Worker stages."""

    def __init__(
        self,
        max_contexts: int,
        drop_policy: DropPolicy | str = DropPolicy.LATEST,
    ) -> None:
        if max_contexts <= 0:
            raise ValueError("max_contexts must be greater than zero")
        self.max_contexts = max_contexts
        self.drop_policy = DropPolicy(drop_policy)
        if self.drop_policy == DropPolicy.LATEST:
            self.drop_policy = DropPolicy.DROP_OLDEST
        self._contexts: deque[PipelineContext] = deque()
        self._dropped_count = 0
        self._max_depth_seen = 0

    def put(self, context: PipelineContext) -> bool:
        if len(self._contexts) < self.max_contexts:
            self._contexts.append(context)
            self._max_depth_seen = max(self._max_depth_seen, len(self._contexts))
            return True
        if self.drop_policy == DropPolicy.DROP_OLDEST:
            self._contexts.popleft()
            self._contexts.append(context)
            self._dropped_count += 1
            return True
        if self.drop_policy in {DropPolicy.DROP_NEWEST, DropPolicy.BLOCK}:
            self._dropped_count += 1
            return False
        raise ValueError(f"unsupported drop policy {self.drop_policy}")

    def drain_all(self) -> list[PipelineContext]:
        contexts = list(self._contexts)
        self._contexts.clear()
        return contexts

    @property
    def metrics(self) -> QueueMetrics:
        return QueueMetrics(len(self._contexts), self._dropped_count, self._max_depth_seen)


@dataclass(frozen=True)
class BatchPolicy:
    max_batch_size: int
    max_wait_ms: int = 20
    drop_policy: DropPolicy | str = DropPolicy.LATEST

    def __post_init__(self) -> None:
        if self.max_batch_size <= 0:
            raise ValueError("max_batch_size must be greater than zero")
        if self.max_wait_ms < 0:
            raise ValueError("max_wait_ms must be zero or greater")
        DropPolicy(self.drop_policy)


class BatchCollector:
    """Collect latest frames per stream without exposing demux logic to users."""

    def __init__(
        self,
        stream_queues: dict[str, FrameQueue],
        policy: BatchPolicy,
    ) -> None:
        self._stream_queues = stream_queues
        self._policy = policy

    def collect(self) -> list[PipelineContext]:
        deadline = monotonic() + (self._policy.max_wait_ms / 1000)
        frames = self._collect_available()
        while not frames and monotonic() < deadline:
            frames = self._collect_available()

        ordered = sorted(frames, key=lambda frame: frame.stream_id)
        capped = ordered[: self._policy.max_batch_size]
        return [PipelineContext(frame=frame) for frame in capped]

    def _collect_available(self) -> list[Frame]:
        frames: list[Frame] = []
        for stream_id in sorted(self._stream_queues):
            frame = self._stream_queues[stream_id].drain_latest()
            if frame is not None:
                frames.append(frame)
        return frames
