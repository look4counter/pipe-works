from dataclasses import dataclass

from pipeworks import (
    DetectionBoxOverlay,
    Frame,
    Pipeline,
    RTSPPublisher,
    Stream,
    YoloInference,
)


@dataclass
class FiniteStream:
    stream_id: str
    count: int

    def stream_frames(self):
        for sequence in range(self.count):
            yield Frame(self.stream_id, image=f"{self.stream_id}:{sequence}", sequence=sequence)


def test_continuous_runner_batches_one_frame_per_stream_cycle() -> None:
    output = RTSPPublisher("memory://out")
    pipeline = (
        Pipeline("continuous")
        .streams([Stream("cam01", "rtsp://one"), Stream("cam02", "rtsp://two")])
        .batch_inference(YoloInference("models/cobble.engine"))
        .overlay(DetectionBoxOverlay())
        .output(output)
    )

    result = pipeline.run_streams(
        {"cam01": FiniteStream("cam01", 2), "cam02": FiniteStream("cam02", 2)},
        max_cycles=2,
    )

    assert result.metrics.frames_processed == 4
    assert result.metrics.batch_size == 2
    assert [context.stream_id for context in result.contexts] == [
        "cam01",
        "cam02",
        "cam01",
        "cam02",
    ]
