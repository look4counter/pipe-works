"""Inference adapter boundaries for optional model runtimes."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from importlib.util import find_spec

from pipeworks.models import DetectionResult, PipelineContext


class InferenceRuntimeUnavailableError(RuntimeError):
    """Raised when a real inference adapter is used without its runtime."""


def is_ultralytics_available() -> bool:
    return find_spec("ultralytics") is not None


def is_tensorrt_available() -> bool:
    return find_spec("tensorrt") is not None


@dataclass
class UltralyticsYoloInference:
    """YOLO adapter boundary.

    Real model invocation is intentionally delayed until `infer()` so importing
    this SDK remains lightweight.
    """

    model: str
    stage: str = "yolo"
    name: str = "UltralyticsYoloInference"
    predictor: Callable[[object, dict[str, object]], list[DetectionResult]] | None = None

    @property
    def available(self) -> bool:
        return is_ultralytics_available()

    def infer(self, context: PipelineContext, settings: dict[str, object]) -> DetectionResult:
        if self.predictor is not None:
            results = self.predictor(context.frame.image, settings)
            if len(results) != 1:
                raise ValueError("Ultralytics predictor must return one DetectionResult")
            result = results[0]
            if result.stream_id != context.stream_id:
                raise ValueError("inference result stream_id does not match context")
            return result
        if not self.available:
            raise InferenceRuntimeUnavailableError(
                "Ultralytics YOLO adapter requires the 'ultralytics' package. "
                "Install the yolo extra or use YoloInference for local deterministic tests."
            )
        raise NotImplementedError("Real Ultralytics invocation is scheduled for the GPU adapter slice.")


@dataclass
class TensorRTInference:
    """TensorRT engine adapter boundary."""

    engine_path: str
    stage: str = "tensorrt"
    name: str = "TensorRTInference"
    runner: Callable[[object, dict[str, object]], DetectionResult] | None = None

    @property
    def available(self) -> bool:
        return is_tensorrt_available()

    @property
    def model(self) -> str:
        return self.engine_path

    def infer(self, context: PipelineContext, settings: dict[str, object]) -> DetectionResult:
        if self.runner is not None:
            result = self.runner(context.frame.image, settings)
            if result.stream_id != context.stream_id:
                raise ValueError("inference result stream_id does not match context")
            return result
        if not self.available:
            raise InferenceRuntimeUnavailableError(
                "TensorRT adapter requires the 'tensorrt' Python package and CUDA runtime. "
                "Install TensorRT in the deployment environment or use YoloInference for local tests."
            )
        raise NotImplementedError("Real TensorRT execution is scheduled for the GPU adapter slice.")
