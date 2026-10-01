"""Inference adapter boundaries for optional model runtimes."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from importlib.util import find_spec
from typing import Protocol, runtime_checkable

from pipeworks.models import Detection, DetectionResult, PipelineContext


class InferenceRuntimeUnavailableError(RuntimeError):
    """Raised when a real inference adapter is used without its runtime."""


@runtime_checkable
class TensorRTSession(Protocol):
    """Vendor-neutral contract around a TensorRT execution context."""

    def infer(self, image: object, settings: dict[str, object]) -> DetectionResult:
        ...

    def infer_batch(
        self, images: list[object], settings: dict[str, object]
    ) -> list[DetectionResult]:
        ...

    def reset(self) -> None:
        """Release and recreate CUDA resources after a runtime error."""


@dataclass
class TensorRTSessionFactory:
    """Cache deployment-specific TensorRT sessions by engine path.

    The SDK owns lifecycle and reuse, while the deployment supplies the loader
    that knows its CUDA bindings, plugins, and execution-context setup.
    """

    loader: Callable[[str], TensorRTSession]
    _sessions: dict[str, TensorRTSession] = field(default_factory=dict, init=False, repr=False)

    def __call__(self, engine_path: str) -> TensorRTSession:
        if engine_path not in self._sessions:
            self._sessions[engine_path] = self.loader(engine_path)
        return self._sessions[engine_path]

    def clear(self, engine_path: str | None = None) -> None:
        """Reset and forget one engine session, or every cached session."""

        paths = [engine_path] if engine_path is not None else list(self._sessions)
        for path in paths:
            session = self._sessions.pop(path, None)
            if session is not None:
                session.reset()


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
    _model: object | None = field(default=None, init=False, repr=False)

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
        return self._infer_real([context], settings)[0]

    def infer_batch(
        self, contexts: list[PipelineContext], settings: dict[str, object]
    ) -> list[DetectionResult]:
        if self.predictor is not None:
            results = [self.predictor(context.frame.image, settings)[0] for context in contexts]
        else:
            results = self._infer_real(contexts, settings)
        _validate_batch_results(contexts, results)
        return results

    def _infer_real(
        self, contexts: list[PipelineContext], settings: dict[str, object]
    ) -> list[DetectionResult]:
        if self._model is None and not self.available:
            raise InferenceRuntimeUnavailableError(
                "Ultralytics YOLO adapter requires the 'ultralytics' package. "
                "Install the yolo extra or use YoloInference for local deterministic tests."
            )
        retries = max(int(settings.get("inference_retry", 0)), 0)
        for attempt in range(retries + 1):
            try:
                if self._model is None:
                    from ultralytics import YOLO

                    self._model = YOLO(self.model)
                results = self._model.predict(
                    source=[context.frame.image for context in contexts],
                    conf=float(settings.get("confidence", 0.5)),
                    device=settings.get("device", "cpu"),
                    half=bool(settings.get("fp16", False)),
                    verbose=False,
                )
                return [
                    _normalize_ultralytics_result(context, raw, self.stage)
                    for context, raw in zip(contexts, results, strict=True)
                ]
            except Exception:
                self._model = None
                if attempt == retries:
                    raise
        raise RuntimeError("unreachable inference retry state")


@dataclass
class TensorRTInference:
    """TensorRT engine adapter boundary."""

    engine_path: str
    stage: str = "tensorrt"
    name: str = "TensorRTInference"
    runner: Callable[[object, dict[str, object]], DetectionResult] | None = None
    batch_runner: Callable[[list[object], dict[str, object]], list[DetectionResult]] | None = None
    session_factory: Callable[[str], TensorRTSession] | None = None
    _session: TensorRTSession | None = field(default=None, init=False, repr=False)

    @property
    def available(self) -> bool:
        return is_tensorrt_available()

    @property
    def model(self) -> str:
        return self.engine_path

    def infer(self, context: PipelineContext, settings: dict[str, object]) -> DetectionResult:
        if self.runner is not None:
            result = _retry_inference(
                lambda: self.runner(context.frame.image, settings),
                int(settings.get("inference_retry", 0)),
            )
            if result.stream_id != context.stream_id:
                raise ValueError("inference result stream_id does not match context")
            return result
        session = self._get_session()
        result = _retry_session(
            lambda: session.infer(context.frame.image, settings),
            session,
            int(settings.get("inference_retry", 0)),
        )
        if result.stream_id != context.stream_id:
            raise ValueError("inference result stream_id does not match context")
        return result

    def infer_batch(
        self, contexts: list[PipelineContext], settings: dict[str, object]
    ) -> list[DetectionResult]:
        if self.batch_runner is not None:
            results = _retry_inference(
                lambda: self.batch_runner([context.frame.image for context in contexts], settings),
                int(settings.get("inference_retry", 0)),
            )
        else:
            session = self._get_session()
            results = _retry_session(
                lambda: session.infer_batch([context.frame.image for context in contexts], settings),
                session,
                int(settings.get("inference_retry", 0)),
            )
        _validate_batch_results(contexts, results)
        return results

    def _get_session(self) -> TensorRTSession:
        if self._session is None:
            if self.session_factory is not None:
                self._session = self.session_factory(self.engine_path)
            elif not self.available:
                raise InferenceRuntimeUnavailableError(
                    "TensorRT adapter requires the 'tensorrt' Python package and CUDA runtime. "
                    "Install TensorRT in the deployment environment or provide session_factory."
                )
            else:
                raise NotImplementedError(
                    "TensorRT is installed, but session_factory is required to configure CUDA bindings."
                )
        return self._session


def _validate_batch_results(
    contexts: list[PipelineContext], results: list[DetectionResult]
) -> None:
    if len(results) != len(contexts):
        raise ValueError("batch inference must return one result per context")
    for context, result in zip(contexts, results, strict=True):
        if result.stream_id != context.stream_id:
            raise ValueError(
                f"batch result stream_id {result.stream_id!r} does not match "
                f"context {context.stream_id!r}"
            )


def _retry_inference(operation: Callable[[], object], retries: int) -> object:
    for attempt in range(max(retries, 0) + 1):
        try:
            return operation()
        except Exception:
            if attempt == retries:
                raise
    raise RuntimeError("unreachable inference retry state")


def _retry_session(
    operation: Callable[[], object], session: TensorRTSession, retries: int
) -> object:
    for attempt in range(max(retries, 0) + 1):
        try:
            return operation()
        except Exception:
            session.reset()
            if attempt == retries:
                raise
    raise RuntimeError("unreachable session retry state")


def _normalize_ultralytics_result(
    context: PipelineContext, raw: object, stage: str
) -> DetectionResult:
    boxes = getattr(raw, "boxes", None)
    xyxy = _as_rows(getattr(boxes, "xyxy", []))
    confidences = _as_values(getattr(boxes, "conf", []))
    classes = _as_values(getattr(boxes, "cls", []))
    names = getattr(raw, "names", {})
    detections = []
    for index, box in enumerate(xyxy):
        class_id = int(classes[index]) if index < len(classes) else 0
        label = names.get(class_id) if isinstance(names, dict) else None
        detections.append(
            Detection(
                box=tuple(float(value) for value in box[:4]),
                confidence=float(confidences[index]) if index < len(confidences) else 0.0,
                class_id=class_id,
                label=label,
            )
        )
    return DetectionResult(
        stream_id=context.stream_id,
        stage=stage,
        detections=detections,
        frame_sequence=context.frame.sequence,
    )


def _as_values(value: object) -> list[object]:
    if hasattr(value, "detach"):
        value = value.detach()
    if hasattr(value, "cpu"):
        value = value.cpu()
    if hasattr(value, "tolist"):
        value = value.tolist()
    if isinstance(value, list):
        return value
    return list(value) if value else []  # type: ignore[arg-type]


def _as_rows(value: object) -> list[list[object]]:
    rows = _as_values(value)
    return [row if isinstance(row, list) else list(row) for row in rows]
