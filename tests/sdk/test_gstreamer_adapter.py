import pytest

from pipeworks.adapters.gstreamer import (
    GStreamerRTSPSource,
    GStreamerUnavailableError,
    is_gstreamer_available,
)


def test_gstreamer_adapter_imports_without_runtime_dependency() -> None:
    source = GStreamerRTSPSource("rtsp://camera/main", stream_id="cam01")

    assert source.stream_id == "cam01"
    assert "rtspsrc location=rtsp://camera/main" in source.pipeline_description()
    assert isinstance(is_gstreamer_available(), bool)


def test_gstreamer_adapter_reports_missing_dependency_when_unavailable() -> None:
    source = GStreamerRTSPSource("rtsp://camera/main")

    if source.available:
        pytest.skip("GStreamer is installed in this environment")

    with pytest.raises(GStreamerUnavailableError, match="GStreamer RTSP adapter requires"):
        source.frames()
