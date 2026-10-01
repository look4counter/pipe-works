"""Pipe Works real-time video pipeline SDK."""

__version__ = "0.1.0"

from pipeworks.components import (
    DetectionBoxOverlay,
    DetectionCrop,
    FileSource,
    MockSource,
    MQPublishAction,
    RTSPPublisher,
    RTSPSource,
    StaticBoxOverlay,
    SvgSendAction,
    SyntheticSource,
    YoloInference,
)
from pipeworks.core.models import (
    AcceptanceCriterion,
    Evidence,
    GateResult,
    LoopDecision,
    Task,
    TaskStatus,
)
from pipeworks.lifecycle import Lifecycle, PipelineState
from pipeworks.loop.engine import LoopEngine
from pipeworks.models import Detection, DetectionResult, Frame, PipelineContext, Stream
from pipeworks.observability import HealthStatus, metrics_json, metrics_prometheus, metrics_snapshot
from pipeworks.pipeline import Pipeline
from pipeworks.plan import PipelinePlan, PipelineStep
from pipeworks.runtime import BatchCollector, BatchPolicy, DropPolicy, FrameQueue, QueueMetrics
from pipeworks.validation import PipelineValidationError, ValidationReport
from pipeworks.workers import (
    ActionWorker,
    BatchInferenceWorker,
    InferenceWorker,
    OutputWorker,
    OverlayWorker,
    ProcessWorker,
    SourceWorker,
    WorkerRuntime,
)

__all__ = [
    "AcceptanceCriterion",
    "ActionWorker",
    "BatchCollector",
    "BatchInferenceWorker",
    "BatchPolicy",
    "Detection",
    "DetectionBoxOverlay",
    "DetectionCrop",
    "DetectionResult",
    "DropPolicy",
    "Evidence",
    "FileSource",
    "Frame",
    "FrameQueue",
    "GateResult",
    "HealthStatus",
    "InferenceWorker",
    "Lifecycle",
    "LoopDecision",
    "LoopEngine",
    "MQPublishAction",
    "MockSource",
    "OutputWorker",
    "OverlayWorker",
    "Pipeline",
    "PipelineContext",
    "PipelinePlan",
    "PipelineState",
    "PipelineStep",
    "PipelineValidationError",
    "ProcessWorker",
    "QueueMetrics",
    "RTSPPublisher",
    "RTSPSource",
    "SourceWorker",
    "StaticBoxOverlay",
    "Stream",
    "SvgSendAction",
    "SyntheticSource",
    "Task",
    "TaskStatus",
    "ValidationReport",
    "WorkerRuntime",
    "YoloInference",
    "__version__",
    "metrics_json",
    "metrics_prometheus",
    "metrics_snapshot",
]
