import json

from pipeworks import MockSource, Pipeline, metrics_json, metrics_prometheus, metrics_snapshot
from pipeworks.models import PipelineMetrics


def test_metrics_are_available_as_dict_json_and_prometheus() -> None:
    metrics = PipelineMetrics(3, 1, 1, 0, 3, 0)

    assert metrics.to_dict()["frames_processed"] == 3
    assert json.loads(metrics_json(metrics))["output_count"] == 3
    assert 'pipeworks_output_count{pipeline="cobble"} 3' in metrics_prometheus("cobble", metrics)


def test_pipeline_health_changes_after_run() -> None:
    pipeline = Pipeline("health").source(MockSource("cam01"))

    assert pipeline.health().status == "starting"
    pipeline.run()
    assert pipeline.health().ready is True
    assert pipeline.health().status == "healthy"


def test_metrics_snapshot_is_json_compatible() -> None:
    metrics = PipelineMetrics(0, 0, 0, 0, 0, 0)

    assert metrics_snapshot(metrics)["duration_ms"] == 0.0
