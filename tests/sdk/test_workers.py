from pipeworks import (
    MockSource,
    Pipeline,
    PipelineContext,
    RTSPPublisher,
    SourceWorker,
    WorkerRuntime,
)
from pipeworks.components import ActionDispatcher


def test_worker_runtime_executes_compiled_steps() -> None:
    output = RTSPPublisher("memory://output")
    pipeline = Pipeline("workers").source(MockSource("cam01")).output(output)
    dispatcher = ActionDispatcher()

    result = WorkerRuntime().run(
        pipeline.compile().steps,
        [PipelineContext(frame=frame) for frame in SourceWorker().run(MockSource("cam01"))],
        pipeline.compile().config,
        dispatcher,
    )
    dispatcher.drain()

    assert len(result.contexts) == 1
    assert result.output_count == 1


def test_pipeline_uses_workers_without_changing_public_result() -> None:
    output = RTSPPublisher("memory://output")
    result = Pipeline("workers").source(MockSource("cam01")).output(output).run()

    assert result.metrics.output_count == 1
    assert output.written[0].stream_id == "cam01"
