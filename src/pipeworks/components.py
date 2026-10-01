"""Public component contracts and built-in MVP components."""

from __future__ import annotations

from concurrent.futures import CancelledError, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from threading import BoundedSemaphore
from time import perf_counter, sleep
from typing import Protocol, runtime_checkable

from pipeworks.models import (
    Detection,
    DetectionResult,
    Frame,
    OverlayCommand,
    PipelineContext,
)


@runtime_checkable
class SourceComponent(Protocol):
    def frames(self) -> list[Frame]:
        """Return frames for MVP execution."""


@runtime_checkable
class InferenceComponent(Protocol):
    name: str

    def infer(self, context: PipelineContext, settings: dict[str, object]) -> DetectionResult:
        """Infer one context."""


@runtime_checkable
class BatchInferenceComponent(Protocol):
    name: str

    def infer_batch(
        self, contexts: list[PipelineContext], settings: dict[str, object]
    ) -> list[DetectionResult]:
        """Infer multiple contexts while preserving order."""


@runtime_checkable
class ProcessorComponent(Protocol):
    def process(self, context: PipelineContext) -> PipelineContext:
        """Transform a context."""


@runtime_checkable
class OverlayComponent(Protocol):
    def apply(self, context: PipelineContext) -> PipelineContext:
        """Add overlay instructions to a context."""


@runtime_checkable
class ActionComponent(Protocol):
    def execute(self, context: PipelineContext, settings: dict[str, object]) -> None:
        """Execute an external side effect."""


@runtime_checkable
class OutputComponent(Protocol):
    def write(self, context: PipelineContext, settings: dict[str, object]) -> None:
        """Publish or store one processed context."""


@dataclass
class MockSource:
    """Deterministic in-memory source for tests and examples."""

    stream_id: str = "default"
    frame_count: int = 1
    payload_prefix: str = "frame"
    name: str = "MockSource"

    def frames(self) -> list[Frame]:
        return [
            Frame(
                stream_id=self.stream_id,
                image=f"{self.payload_prefix}-{self.stream_id}-{index}",
                sequence=index,
            )
            for index in range(self.frame_count)
        ]


@dataclass
class SyntheticSource:
    """Synthetic video source for local development and tests."""

    stream_id: str = "synthetic"
    frame_count: int = 5
    width: int = 640
    height: int = 360
    name: str = "SyntheticSource"

    def frames(self) -> list[Frame]:
        return [
            Frame(
                stream_id=self.stream_id,
                image=f"synthetic:{self.width}x{self.height}:{index}",
                sequence=index,
                metadata={"width": self.width, "height": self.height},
            )
            for index in range(self.frame_count)
        ]


@dataclass
class FileSource:
    """Local file descriptor source.

    MVP stores the file path in frame payload; real decode is a future adapter.
    """

    path: str
    stream_id: str = "file"
    name: str = "FileSource"

    def frames(self) -> list[Frame]:
        return [
            Frame(
                stream_id=self.stream_id,
                image=self.path,
                sequence=0,
                metadata={"path": self.path},
            )
        ]


@dataclass
class RTSPSource:
    """Public RTSP source descriptor.

    Real network ingest is a future adapter. For MVP this component acts as a
    readable descriptor and produces one placeholder frame when run locally.
    """

    url: str
    stream_id: str = "default"
    name: str = "RTSPSource"

    def frames(self) -> list[Frame]:
        return [Frame(stream_id=self.stream_id, image=self.url, sequence=0)]


@dataclass
class YoloInference:
    """MVP inference descriptor with deterministic fake results."""

    model: str
    stage: str | None = None
    name: str = "YoloInference"

    def __post_init__(self) -> None:
        if self.stage is None:
            self.stage = str(self.name)

    def infer(self, context: PipelineContext, settings: dict[str, object]) -> DetectionResult:
        confidence = float(settings.get("confidence", 0.5))
        return DetectionResult(
            stream_id=context.stream_id,
            stage=str(self.stage),
            frame_sequence=context.frame.sequence,
            detections=[
                Detection(
                    box=(10.0, 10.0, 50.0, 50.0),
                    confidence=confidence,
                    class_id=0,
                    label="object",
                    attributes={"model": self.model},
                )
            ],
        )

    def infer_batch(
        self, contexts: list[PipelineContext], settings: dict[str, object]
    ) -> list[DetectionResult]:
        return [self.infer(context, settings) for context in contexts]


@dataclass
class DetectionCrop:
    """Records crop intents based on latest detections."""

    name: str = "DetectionCrop"

    def process(self, context: PipelineContext) -> PipelineContext:
        context.data["crops"] = [detection.box for detection in context.detections]
        return context


@dataclass
class StaticBoxOverlay:
    box: tuple[float, float, float, float] = (0.0, 0.0, 100.0, 100.0)
    name: str = "StaticBoxOverlay"

    def apply(self, context: PipelineContext) -> PipelineContext:
        context.overlays.append(OverlayCommand(kind="static_box", payload={"box": self.box}))
        return context


@dataclass
class DetectionBoxOverlay:
    name: str = "DetectionBoxOverlay"

    def apply(self, context: PipelineContext) -> PipelineContext:
        for detection in context.detections:
            context.overlays.append(
                OverlayCommand(
                    kind="detection_box",
                    payload={
                        "box": detection.box,
                        "confidence": detection.confidence,
                        "class_id": detection.class_id,
                    },
                )
            )
        return context


@dataclass
class SvgSendAction:
    url: str
    delay_s: float = 0.0
    sent: list[str] = field(default_factory=list)
    name: str = "SvgSendAction"

    def execute(self, context: PipelineContext, settings: dict[str, object]) -> None:
        if self.delay_s:
            sleep(self.delay_s)
        self.sent.append(context.stream_id)


@dataclass
class MQPublishAction:
    topic: str
    published: list[str] = field(default_factory=list)
    name: str = "MQPublishAction"

    def execute(self, context: PipelineContext, settings: dict[str, object]) -> None:
        self.published.append(f"{self.topic}:{context.stream_id}")


@dataclass
class RTSPPublisher:
    url: str
    written: list[PipelineContext] = field(default_factory=list)
    name: str = "RTSPPublisher"

    def write(self, context: PipelineContext, settings: dict[str, object]) -> None:
        self.written.append(context)


class ActionDispatcher:
    """Bounded dispatcher hiding action execution from the video path."""

    def __init__(self, max_workers: int = 4, max_pending: int = 64) -> None:
        if max_workers <= 0 or max_pending <= 0:
            raise ValueError("max_workers and max_pending must be greater than zero")
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._slots = BoundedSemaphore(max_pending)
        self._futures: list[Future[None]] = []
        self._started_at: dict[Future[None], float] = {}
        self.scheduled = 0
        self.completed = 0
        self.errors = 0
        self.dropped = 0
        self.latency_ms: list[float] = []
        self._contexts: dict[Future[None], PipelineContext] = {}
        self._closed = False

    def submit(
        self, action: ActionComponent, context: PipelineContext, settings: dict[str, object]
    ) -> bool:
        if self._closed:
            self.dropped += 1
            context.errors.append("action dispatcher is closed")
            return False
        if not self._slots.acquire(blocking=False):
            self.dropped += 1
            context.errors.append(f"action queue full: dropped {action.__class__.__name__}")
            return False
        self.scheduled += 1
        try:
            future = self._executor.submit(action.execute, context, settings)
        except Exception:
            self._slots.release()
            raise
        self._started_at[future] = perf_counter()
        self._contexts[future] = context
        future.add_done_callback(self._on_done)
        self._futures.append(future)
        return True

    def drain(self, timeout: float | None = None, wait_for_actions: bool = True) -> None:
        self._closed = True
        if wait_for_actions and self._futures:
            wait(self._futures, timeout=timeout)
        self._executor.shutdown(wait=wait_for_actions)

    def close(self, timeout: float | None = None) -> None:
        """Gracefully stop accepting actions and drain pending work."""

        self.drain(timeout=timeout, wait_for_actions=True)

    def _on_done(self, future: Future[None]) -> None:
        self._slots.release()
        started_at = self._started_at.pop(future, None)
        context = self._contexts.pop(future, None)
        if started_at is not None:
            self.latency_ms.append((perf_counter() - started_at) * 1000)
        try:
            exception = future.exception()
        except CancelledError:
            self.errors += 1
            return
        if exception is not None:
            self.errors += 1
            if context is not None:
                context.errors.append(f"action failed: {exception}")
            return
        self.completed += 1
