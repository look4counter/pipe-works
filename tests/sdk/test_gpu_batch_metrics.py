from pipeworks import Frame, Pipeline, Stream, YoloInference


def test_batch_metrics_report_gpu_scheduling_shape() -> None:
    result = (
        Pipeline("batch-metrics")
        .streams([Stream("cam01", "rtsp://one"), Stream("cam02", "rtsp://two")])
        .batch_inference(YoloInference("models/cobble.engine"))
        .run()
    )

    assert result.metrics.batch_count == 1
    assert result.metrics.batch_items == 2
    assert result.metrics.inference_latency_ms >= 0


def test_continuous_batch_metrics_accumulate_per_cycle() -> None:
    class Source:
        def __init__(self, stream_id: str) -> None:
            self.stream_id = stream_id

        def stream_frames(self):
            yield Frame(self.stream_id, sequence=0)
            yield Frame(self.stream_id, sequence=1)

    result = (
        Pipeline("continuous-batch-metrics")
        .streams([Stream("cam01", "rtsp://one"), Stream("cam02", "rtsp://two")])
        .batch_inference(YoloInference("models/cobble.engine"))
        .run_streams({"cam01": Source("cam01"), "cam02": Source("cam02")}, max_cycles=2)
    )

    assert result.metrics.batch_count == 2
    assert result.metrics.batch_items == 4
