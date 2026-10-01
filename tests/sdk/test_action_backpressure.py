from pipeworks import MockSource, Pipeline, SvgSendAction
from pipeworks.components import ActionDispatcher
from pipeworks.models import Frame, PipelineContext


def test_action_dispatcher_drops_when_bounded_queue_is_full() -> None:
    dispatcher = ActionDispatcher(max_workers=1, max_pending=1)
    action = SvgSendAction("http://events", delay_s=0.1)
    first = PipelineContext(Frame("cam01", sequence=0))
    second = PipelineContext(Frame("cam01", sequence=1))

    assert dispatcher.submit(action, first, {}) is True
    assert dispatcher.submit(action, second, {}) is False
    dispatcher.drain()

    assert dispatcher.scheduled == 1
    assert dispatcher.dropped == 1
    assert "action queue full" in second.errors[0]


def test_pipeline_reports_action_drops_in_metrics(tmp_path) -> None:
    config = tmp_path / "pipeworks.yaml"
    config.write_text(
        "Action:\n  max_workers: 1\n  max_pending: 1\n",
        encoding="utf-8",
    )
    result = (
        Pipeline("bounded-actions", config=config)
        .source(MockSource("cam01", frame_count=3))
        .action(SvgSendAction("http://events", delay_s=0.1))
        .run()
    )

    assert result.metrics.actions_dropped >= 1
    assert result.metrics.error_count >= result.metrics.actions_dropped
