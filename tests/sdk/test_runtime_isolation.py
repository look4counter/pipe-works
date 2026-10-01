from pipeworks import MockSource, Pipeline, PipelineContext


class FailsForSecondFrame:
    def process(self, context: PipelineContext) -> PipelineContext:
        if context.frame.sequence == 1:
            raise RuntimeError("bad frame")
        return context


class FailsForSecondOutput:
    def write(self, context: PipelineContext, settings: dict[str, object]) -> None:
        if context.frame.sequence == 1:
            raise RuntimeError("output unavailable")


def test_worker_isolates_processor_failure_to_one_context(tmp_path) -> None:
    config = tmp_path / "pipeworks.yaml"
    config.write_text("Pipeline:\n  isolate_errors: true\n", encoding="utf-8")
    result = (
        Pipeline("isolated-process", config=config)
        .source(MockSource("cam01", frame_count=3))
        .process(FailsForSecondFrame())
        .run()
    )

    assert len(result.contexts) == 3
    assert result.contexts[1].errors == ["process failed: bad frame"]
    assert result.contexts[0].errors == []
    assert result.contexts[2].errors == []


def test_worker_isolates_output_failure_and_counts_successes(tmp_path) -> None:
    config = tmp_path / "pipeworks.yaml"
    config.write_text("Pipeline:\n  isolate_errors: true\n", encoding="utf-8")
    result = (
        Pipeline("isolated-output", config=config)
        .source(MockSource("cam01", frame_count=3))
        .output(FailsForSecondOutput())
        .run()
    )

    assert result.metrics.output_count == 2
    assert result.metrics.error_count == 1
