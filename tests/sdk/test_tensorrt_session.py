from dataclasses import dataclass

from pipeworks import Frame, PipelineContext
from pipeworks.adapters.inference import TensorRTInference, TensorRTSessionFactory
from pipeworks.models import DetectionResult


@dataclass
class FakeTensorRTSession:
    resets: int = 0
    calls: int = 0

    def infer(self, image, settings):
        self.calls += 1
        return DetectionResult("cam01", "tensorrt", [], 0)

    def infer_batch(self, images, settings):
        return [DetectionResult(f"cam0{index + 1}", "tensorrt", [], 0) for index in range(len(images))]

    def reset(self) -> None:
        self.resets += 1


def test_tensorrt_session_factory_is_lazy_and_reused() -> None:
    session = FakeTensorRTSession()
    factories: list[str] = []
    adapter = TensorRTInference(
        "models/cobble.engine",
        session_factory=lambda path: (factories.append(path) or session),
    )

    first = adapter.infer(PipelineContext(Frame("cam01")), {})
    second = adapter.infer(PipelineContext(Frame("cam01", sequence=1)), {})

    assert first.stage == "tensorrt"
    assert second.frame_sequence == 0
    assert factories == ["models/cobble.engine"]
    assert session.calls == 2


def test_tensorrt_session_batch_preserves_stream_mapping() -> None:
    session = FakeTensorRTSession()
    adapter = TensorRTInference("models/cobble.engine", session_factory=lambda path: session)
    contexts = [PipelineContext(Frame("cam01")), PipelineContext(Frame("cam02"))]

    results = adapter.infer_batch(contexts, {})

    assert [result.stream_id for result in results] == ["cam01", "cam02"]


def test_tensorrt_session_factory_caches_per_engine_and_clears() -> None:
    created: dict[str, list[FakeTensorRTSession]] = {}

    def load(path: str) -> FakeTensorRTSession:
        session = FakeTensorRTSession()
        created.setdefault(path, []).append(session)
        return session

    factory = TensorRTSessionFactory(
        loader=load
    )

    first = factory("models/one.engine")
    assert factory("models/one.engine") is first
    second = factory("models/two.engine")

    factory.clear("models/one.engine")
    assert first.resets == 1
    assert factory("models/one.engine") is not first
    factory.clear()
    assert second.resets == 1
    assert len(created["models/one.engine"]) == 2
