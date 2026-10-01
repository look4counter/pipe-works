import pytest

from pipeworks import MockSource, Pipeline, PipelineState


def test_pipeline_state_starts_created_and_stops_after_successful_run() -> None:
    pipeline = Pipeline("lifecycle").source(MockSource("cam01"))

    assert pipeline.state == PipelineState.CREATED

    result = pipeline.run()

    assert pipeline.state == PipelineState.STOPPED
    assert result.state == "stopped"


def test_pipeline_state_moves_to_error_when_component_fails() -> None:
    class FailingProcessor:
        def process(self, context):
            raise RuntimeError("boom")

    pipeline = Pipeline("failing").source(MockSource("cam01")).process(FailingProcessor())

    with pytest.raises(RuntimeError, match="boom"):
        pipeline.run()

    assert pipeline.state == PipelineState.ERROR
