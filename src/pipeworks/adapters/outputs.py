"""Output adapter boundaries."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from pipeworks.models import PipelineContext


@dataclass
class MediaMTXPublisher:
    """MediaMTX output descriptor.

    MVP records contexts and preserves URL identity. Real encoded frame publish
    is a future media adapter slice.
    """

    url: str
    name: str = "MediaMTXPublisher"
    written: list[PipelineContext] = field(default_factory=list)
    publisher: Callable[[str, PipelineContext, dict[str, object]], None] | None = None

    def write(self, context: PipelineContext, settings: dict[str, object]) -> None:
        output_url = self.url.format(stream_id=context.stream_id)
        context.frame.metadata["output_url"] = output_url
        if self.publisher is not None:
            self.publisher(output_url, context, settings)
        self.written.append(context)
