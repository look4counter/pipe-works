import pytest

from pipeworks import Frame, PipelineContext
from pipeworks.adapters.inference import (
    InferenceRuntimeUnavailableError,
    TensorRTInference,
    UltralyticsYoloInference,
    is_tensorrt_available,
    is_ultralytics_available,
)


def test_ultralytics_adapter_boundary_preserves_model_identity() -> None:
    adapter = UltralyticsYoloInference("models/cobble.pt", stage="primary")

    assert adapter.model == "models/cobble.pt"
    assert adapter.stage == "primary"
    assert isinstance(is_ultralytics_available(), bool)


def test_tensorrt_adapter_boundary_preserves_engine_identity() -> None:
    adapter = TensorRTInference("models/cobble.engine", stage="primary")

    assert adapter.model == "models/cobble.engine"
    assert adapter.stage == "primary"
    assert isinstance(is_tensorrt_available(), bool)


def test_missing_ultralytics_runtime_raises_actionable_error() -> None:
    adapter = UltralyticsYoloInference("models/cobble.pt")
    if adapter.available:
        pytest.skip("Ultralytics is installed in this environment")

    with pytest.raises(InferenceRuntimeUnavailableError, match="ultralytics"):
        adapter.infer(PipelineContext(Frame("cam01")), {})


def test_missing_tensorrt_runtime_raises_actionable_error() -> None:
    adapter = TensorRTInference("models/cobble.engine")
    if adapter.available:
        pytest.skip("TensorRT is installed in this environment")

    with pytest.raises(InferenceRuntimeUnavailableError, match="TensorRT"):
        adapter.infer(PipelineContext(Frame("cam01")), {})
