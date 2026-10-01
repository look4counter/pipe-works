"""GStreamer RTSP adapter boundary.

The adapter is intentionally lazy: importing this module does not require
PyGObject/GStreamer. Real frame ingest is enabled only when those dependencies
are installed in the runtime environment.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from importlib.util import find_spec
from typing import Any

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
        return list(self.stream_frames())

    def stream_frames(self) -> Iterator[Frame]:
        """Yield decoded appsink payloads until the source reaches EOS."""

        if self.frame_reader is not None:
            yield from self.frame_reader(self.url, self.stream_id)
            return
        if not self.available:
            raise GStreamerUnavailableError(
                "GStreamer RTSP adapter requires PyGObject and GStreamer runtime. "
                "Install GStreamer 1.20+ and PyGObject, or use SyntheticSource/FileSource "
                "for local tests."
            )
        import gi

        gi.require_version("Gst", "1.0")
        from gi.repository import Gst

        Gst.init(None)
        pipeline = Gst.parse_launch(
            self.pipeline_description().replace("! appsink", "! appsink name=pipeworks_sink")
        )
        sink = pipeline.get_by_name("pipeworks_sink")
        if sink is None:
            raise RuntimeError("GStreamer pipeline did not create the appsink")
        pipeline.set_state(Gst.State.PLAYING)
        sequence = 0
        try:
            while True:
                sample = sink.emit("pull-sample")
                if sample is None:
                    break
                buffer = sample.get_buffer()
                if buffer is None:
                    continue
                success, mapped = buffer.map(Gst.MapFlags.READ)
                if not success:
                    continue
                try:
                    caps = sample.get_caps()
                    structure = caps.get_structure(0) if caps is not None else None
                    metadata: dict[str, Any] = {"gstreamer_pipeline": self.pipeline_description()}
                    if structure is not None:
                        metadata["format"] = structure.get_string("format")
                        metadata["width"] = structure.get_value("width")
                        metadata["height"] = structure.get_value("height")
                    yield Frame(
                        stream_id=self.stream_id,
                        image=bytes(mapped.data),
                        sequence=sequence,
                        metadata=metadata,
                    )
                    sequence += 1
                finally:
                    buffer.unmap(mapped)
        finally:
            pipeline.set_state(Gst.State.NULL)
