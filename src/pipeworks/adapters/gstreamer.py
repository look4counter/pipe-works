"""GStreamer RTSP adapter boundary.

The adapter is intentionally lazy: importing this module does not require
PyGObject/GStreamer. Real frame ingest is enabled only when those dependencies
are installed in the runtime environment.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from importlib.util import find_spec

from pipeworks.models import Frame


class GStreamerUnavailableError(RuntimeError):
    """Raised when the real GStreamer adapter is used without dependencies."""


def is_gstreamer_available() -> bool:
    return find_spec("gi") is not None


@dataclass
class GStreamerRTSPSource:
    """RTSP source adapter backed by GStreamer when available."""

    url: str
    stream_id: str = "default"
    name: str = "GStreamerRTSPSource"
    frame_reader: Callable[[str, str], Iterable[Frame]] | None = None

    @property
    def available(self) -> bool:
        return is_gstreamer_available()

    def pipeline_description(self) -> str:
        return (
            f"rtspsrc location={self.url} latency=0 ! "
            "rtph264depay ! h264parse ! avdec_h264 ! videoconvert ! appsink"
        )

    def frames(self) -> list[Frame]:
        if self.frame_reader is not None:
            return list(self.frame_reader(self.url, self.stream_id))
        if not self.available:
            raise GStreamerUnavailableError(
                "GStreamer RTSP adapter requires PyGObject and GStreamer runtime. "
                "Install GStreamer 1.20+ and PyGObject, or use SyntheticSource/FileSource "
                "for local tests."
            )
        # Real appsink frame extraction is a follow-up integration slice. Keep a
        # descriptor frame so the adapter can participate in dry-run pipelines.
        return [
            Frame(
                stream_id=self.stream_id,
                image=self.url,
                sequence=0,
                metadata={"gstreamer_pipeline": self.pipeline_description()},
            )
        ]
