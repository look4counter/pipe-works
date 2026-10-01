"""Compiled, read-only representation of a declared pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pipeworks.config import RuntimeConfig
from pipeworks.models import Stream


@dataclass(frozen=True)
class PipelineStep:
    kind: str
    component: object


@dataclass(frozen=True)
class PipelinePlan:
    """The executable shape produced from the public Pipeline DSL."""

    name: str
    source: object | None
    streams: tuple[Stream, ...]
    steps: tuple[PipelineStep, ...]
    config: RuntimeConfig

    @property
    def has_batch_inference(self) -> bool:
        return any(step.kind == "batch_inference" for step in self.steps)

    @property
    def config_summary(self) -> dict[str, dict[str, Any]]:
        return {section: dict(values) for section, values in self.config.sections.items()}

    def describe(self) -> list[str]:
        lines = [f"Pipeline({self.name})"]
        if self.source is not None:
            lines.append(f"source: {self.describe_component(self.source)}")
        if self.streams:
            lines.append(f"streams: {', '.join(stream.stream_id for stream in self.streams)}")
        for step in self.steps:
            lines.append(f"{step.kind}: {self.describe_component(step.component)}")
        return lines

    @staticmethod
    def describe_component(component: Any) -> str:
        values: list[str] = []
        for attr in ("url", "model", "topic", "stream_id"):
            if hasattr(component, attr):
                value = getattr(component, attr)
                if value:
                    values.append(f"{attr}={value}")
        suffix = f"({', '.join(values)})" if values else ""
        return f"{component.__class__.__name__}{suffix}"
