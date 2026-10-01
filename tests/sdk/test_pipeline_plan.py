from pipeworks import MockSource, Pipeline, PipelinePlan, YoloInference


def test_compile_returns_read_only_pipeline_shape_without_running() -> None:
    pipeline = (
        Pipeline("compiled")
        .source(MockSource("cam01"))
        .inference(YoloInference("models/cobble.engine"))
    )

    plan = pipeline.compile()

    assert isinstance(plan, PipelinePlan)
    assert plan.name == "compiled"
    assert plan.source is not None
    assert [step.kind for step in plan.steps] == ["inference"]
    assert plan.steps[0].component.model == "models/cobble.engine"
    assert plan.has_batch_inference is False
    assert pipeline.state.value == "created"


def test_compile_preserves_batch_semantics_and_config_summary(tmp_path) -> None:
    config_path = tmp_path / "pipeworks.yaml"
    config_path.write_text("BatchInference:\n  max_batch_size: 4\n", encoding="utf-8")

    plan = (
        Pipeline("batch-plan", config=config_path)
        .batch_inference(YoloInference("models/cobble.engine"))
        .compile()
    )

    assert plan.has_batch_inference is True
    assert plan.config_summary["BatchInference"]["max_batch_size"] == 4

    summary = plan.config_summary
    summary["BatchInference"]["max_batch_size"] = 99
    assert plan.config_summary["BatchInference"]["max_batch_size"] == 4
