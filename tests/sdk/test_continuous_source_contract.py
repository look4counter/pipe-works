from pipeworks import Frame
from pipeworks.adapters.gstreamer import GStreamerRTSPSource
from pipeworks.config import RuntimeConfig
from pipeworks.workers import SourceWorker


def test_source_worker_exposes_lazy_stream_contract() -> None:
    source = GStreamerRTSPSource(
        "rtsp://camera/main",
        frame_reader=lambda url, stream_id: (Frame(stream_id, sequence=index) for index in range(3)),
    )

    frames = list(SourceWorker().stream(source, RuntimeConfig.defaults()))

    assert [frame.sequence for frame in frames] == [0, 1, 2]
