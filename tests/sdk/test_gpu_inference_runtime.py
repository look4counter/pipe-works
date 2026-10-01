from dataclasses import dataclass

from pipeworks import Frame, PipelineContext
from pipeworks.adapters.inference import TensorRTInference, UltralyticsYoloInference


@dataclass
class FakeTensor:
    value: object

    def cpu(self):
        return self

    def tolist(self):
        return self.value


@dataclass
class FakeBoxes:
    xyxy: FakeTensor
    conf: FakeTensor
    cls: FakeTensor


@dataclass
class FakeUltralyticsResult:
    boxes: FakeBoxes
    names: dict[int, str]


def test_ultralytics_result_is_normalized_to_sdk_detection() -> None:
    context = PipelineContext(Frame("cam01", sequence=4))
    adapter = UltralyticsYoloInference("model.pt")
    raw = FakeUltralyticsResult(
        FakeBoxes(FakeTensor([[1, 2, 30, 40]]), FakeTensor([0.85]), FakeTensor([2])),
        {2: "cobble"},
    )
    adapter._model = type(
        "FakeModel",
        (),
        {"predict": lambda self, **kwargs: [raw]},
    )()

    result = adapter.infer(context, {})

    assert result.detections[0].label == "cobble"
    assert result.detections[0].confidence == 0.85
    assert result.detections[0].box == (1.0, 2.0, 30.0, 40.0)


def test_tensorrt_runner_retries_transient_failure() -> None:
    attempts = 0
    context = PipelineContext(Frame("cam01"))

    def runner(image, settings):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("cuda temporarily unavailable")
        from pipeworks.models import DetectionResult

        return DetectionResult("cam01", "trt", [], 0)

    result = TensorRTInference("model.engine", runner=runner).infer(
        context, {"inference_retry": 1}
    )

    assert result.stream_id == "cam01"
    assert attempts == 2
