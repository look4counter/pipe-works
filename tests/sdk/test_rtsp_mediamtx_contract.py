from dataclasses import dataclass

from pipeworks import Frame, Pipeline, Stream, YoloInference
from pipeworks.adapters.gstreamer import GStreamerRTSPSource
from pipeworks.adapters.outputs import MediaMTXPublisher


@dataclass
class FakeAppsinkReader:
    """장비 없이도 GStreamer 입력 계약을 재현하는 유한 프레임 리더."""

    count: int = 2

    def __call__(self, url: str, stream_id: str):
        for sequence in range(self.count):
            yield Frame(
                stream_id,
                image=f"decoded:{url}:{sequence}",
                sequence=sequence,
                metadata={"format": "RGB", "width": 1280, "height": 720},
            )


def test_gstreamer_rtsp_to_mediamtx_preserves_stream_identity_and_output_route() -> None:
    published: list[tuple[str, str, int]] = []
    output = MediaMTXPublisher(
        "rtsp://mediamtx/{stream_id}",
        publisher=lambda url, context, settings: published.append(
            (url.replace("{stream_id}", context.stream_id), context.stream_id, context.frame.sequence)
        ),
    )
    pipeline = (
        Pipeline("rtsp-to-mediamtx")
        .streams(
            [
                Stream("cam01", source="rtsp://cam01", output="rtsp://mediamtx/cam01"),
                Stream("cam02", source="rtsp://cam02", output="rtsp://mediamtx/cam02"),
            ]
        )
        .batch_inference(YoloInference("models/cobble.engine"))
        .output(output)
    )

    result = pipeline.run_streams(
        {
            "cam01": GStreamerRTSPSource("rtsp://cam01", "cam01", frame_reader=FakeAppsinkReader()),
            "cam02": GStreamerRTSPSource("rtsp://cam02", "cam02", frame_reader=FakeAppsinkReader()),
        },
        max_cycles=2,
    )

    assert published == [
        ("rtsp://mediamtx/cam01", "cam01", 0),
        ("rtsp://mediamtx/cam02", "cam02", 0),
        ("rtsp://mediamtx/cam01", "cam01", 1),
        ("rtsp://mediamtx/cam02", "cam02", 1),
    ]
    assert result.metrics.frames_processed == 4
    assert result.metrics.batch_count == 2
    assert result.metrics.batch_items == 4
