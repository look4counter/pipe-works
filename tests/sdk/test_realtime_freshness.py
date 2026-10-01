from time import sleep, time

from pipeworks import Frame, Pipeline, RTSPPublisher, YoloInference


class TimestampedSource:
    def __init__(self, timestamp: float) -> None:
        self.timestamp = timestamp

    def frames(self) -> list[Frame]:
        return [Frame("cam01", image="frame", timestamp=self.timestamp)]


class SlowProcessor:
    def process(self, context):
        sleep(0.02)
        return context


def test_expired_frame_is_dropped_before_output(tmp_path) -> None:
    config = tmp_path / "realtime.yaml"
    config.write_text(
        "Realtime:\n  max_frame_age_ms: 100\n  drop_expired_frames: true\n",
        encoding="utf-8",
    )
    output = RTSPPublisher("memory://output")

    result = (
        Pipeline("freshness", config=config)
        .source(TimestampedSource(time() - 1.0))
        .inference(YoloInference("models/cobble.engine"))
        .output(output)
        .run()
    )

    assert result.contexts == []
    assert result.metrics.output_count == 0
    assert result.metrics.expired_frames_dropped == 1
    assert output.written == []


def test_output_latency_is_recorded_for_fresh_frame() -> None:
    output = RTSPPublisher("memory://output")

    result = (
        Pipeline("freshness")
        .source(TimestampedSource(time()))
        .inference(YoloInference("models/cobble.engine"))
        .output(output)
        .run()
    )

    assert result.metrics.expired_frames_dropped == 0
    assert result.metrics.output_count == 1
    assert result.metrics.end_to_end_latency_ms_max >= 0
    assert result.metrics.end_to_end_latency_ms_avg >= 0
    assert result.metrics.end_to_end_latency_ms_p95 >= 0


def test_frame_expiring_between_stages_is_dropped_before_output(tmp_path) -> None:
    config = tmp_path / "realtime.yaml"
    config.write_text(
        "Realtime:\n  max_frame_age_ms: 10\n  drop_expired_frames: true\n",
        encoding="utf-8",
    )
    output = RTSPPublisher("memory://output")

    result = (
        Pipeline("stage-freshness", config=config)
        .source(TimestampedSource(time()))
        .process(SlowProcessor())
        .output(output)
        .run()
    )

    assert result.metrics.expired_frames_dropped == 1
    assert result.metrics.output_count == 0
