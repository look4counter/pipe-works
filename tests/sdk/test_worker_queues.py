from pathlib import Path

from pipeworks import MockSource, Pipeline


class Passthrough:
    def process(self, context):
        return context


def test_worker_queue_applies_latest_drop_policy_between_stages(tmp_path: Path) -> None:
    config = tmp_path / "pipeworks.yaml"
    config.write_text(
        "Pipeline:\n  worker_queue_size: 1\n  worker_drop_policy: latest\n",
        encoding="utf-8",
    )
    result = Pipeline("worker-queue", config=config).source(
        MockSource("cam01", frame_count=3)
    ).process(Passthrough()).run()

    assert [context.frame.sequence for context in result.contexts] == [2]
    assert result.metrics.queue_dropped == 2
