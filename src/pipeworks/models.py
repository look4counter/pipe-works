"""Public data models for the video pipeline SDK."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from time import time
from typing import Any


@dataclass(frozen=True)
class Stream:
    """Named stream declaration for multi-stream pipelines."""

    stream_id: str
    source: str
    output: str | None = None


@dataclass(frozen=True)
class Frame:
    """A stream-aware frame payload."""

    stream_id: str
    image: Any = None
    timestamp: float = field(default_factory=time)
    sequence: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Detection:
    """Normalized detection metadata owned by the SDK."""

    box: tuple[float, float, float, float]
    confidence: float
    class_id: int
    label: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DetectionResult:
    """Inference result mapped back to a stream and inference stage."""

    stream_id: str
    stage: str
    detections: list[Detection]
    frame_sequence: int
    timestamp: float = field(default_factory=time)
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OverlayCommand:
    """Declarative overlay instruction produced by overlay components."""

    kind: str
    payload: dict[str, Any]


@dataclass
class PipelineContext:
    """The runtime currency passed between pipeline components."""

    frame: Frame
    results: dict[str, DetectionResult] = field(default_factory=dict)
    overlays: list[OverlayCommand] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)

    @property
    def stream_id(self) -> str:
        return self.frame.stream_id

    @property
    def detections(self) -> list[Detection]:
        if not self.results:
            return []
        latest_stage = next(reversed(self.results))
        return self.results[latest_stage].detections

    @detections.setter
    def detections(self, value: list[Detection]) -> None:
        stage = next(reversed(self.results), "custom")
        self.results[stage] = DetectionResult(
            stream_id=self.stream_id,
            stage=stage,
            detections=value,
            frame_sequence=self.frame.sequence,
        )

    def add_result(self, result: DetectionResult) -> None:
        if result.stream_id != self.stream_id:
            raise ValueError(
                f"result stream_id {result.stream_id!r} does not match context {self.stream_id!r}"
            )
        self.results[result.stage] = result


@dataclass(frozen=True)
class PipelineMetrics:
    """Small MVP metrics summary."""

    frames_processed: int
    actions_scheduled: int
    actions_completed: int
    action_errors: int
    output_count: int
    error_count: int
    queue_dropped: int = 0
    queue_max_depth: int = 0
    batch_size: int = 0
    duration_ms: float = 0.0
    effective_fps: float = 0.0
    action_latency_ms_max: float = 0.0
    action_latency_ms_avg: float = 0.0
    actions_dropped: int = 0
    batch_count: int = 0
    batch_items: int = 0
    inference_latency_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "frames_processed": self.frames_processed,
            "actions_scheduled": self.actions_scheduled,
            "actions_completed": self.actions_completed,
            "action_errors": self.action_errors,
            "output_count": self.output_count,
            "error_count": self.error_count,
            "queue_dropped": self.queue_dropped,
            "queue_max_depth": self.queue_max_depth,
            "batch_size": self.batch_size,
            "duration_ms": self.duration_ms,
            "effective_fps": self.effective_fps,
            "action_latency_ms_max": self.action_latency_ms_max,
            "action_latency_ms_avg": self.action_latency_ms_avg,
            "actions_dropped": self.actions_dropped,
            "batch_count": self.batch_count,
            "batch_items": self.batch_items,
            "inference_latency_ms": self.inference_latency_ms,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)


@dataclass(frozen=True)
class PipelineResult:
    """Return value from `Pipeline.run()`."""

    pipeline_name: str
    contexts: list[PipelineContext]
    metrics: PipelineMetrics
    state: str = "stopped"
