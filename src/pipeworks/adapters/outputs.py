"""Output adapter boundaries."""

from __future__ import annotations

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

    def write(self, context: PipelineContext, settings: dict[str, object]) -> None:
        context.frame.metadata["output_url"] = self.url
        self.written.append(context)
