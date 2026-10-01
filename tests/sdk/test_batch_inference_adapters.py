import pytest

from pipeworks import Frame, PipelineContext
from pipeworks.adapters.inference import TensorRTInference, UltralyticsYoloInference
from pipeworks.models import DetectionResult


def _result(stream_id: str, stage: str) -> DetectionResult:
    return DetectionResult(stream_id, stage, [], 0)


def test_tensorrt_batch_runner_preserves_context_order_and_identity() -> None:
    contexts = [PipelineContext(Frame("cam01")), PipelineContext(Frame("cam02"))]
    adapter = TensorRTInference(
        "model.engine",
        batch_runner=lambda images, settings: [_result("cam01", "trt"), _result("cam02", "trt")],
    )

    results = adapter.infer_batch(contexts, {})

    assert [result.stream_id for result in results] == ["cam01", "cam02"]


def test_ultralytics_batch_runner_rejects_wrong_stream_mapping() -> None:
    contexts = [PipelineContext(Frame("cam01")), PipelineContext(Frame("cam02"))]
    adapter = UltralyticsYoloInference(
        "model.pt",
        predictor=lambda image, settings: [_result("cam01", "yolo")],
    )

    with pytest.raises(ValueError, match="stream_id"):
        adapter.infer_batch(contexts, {})
