"""Operational metrics and health representations."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

from pipeworks.lifecycle import PipelineState
from pipeworks.models import PipelineMetrics


@dataclass(frozen=True)
class HealthStatus:
    pipeline_name: str
    state: str
    status: str
    ready: bool
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)


def metrics_snapshot(metrics: PipelineMetrics) -> dict[str, Any]:
    return asdict(metrics)


def metrics_json(metrics: PipelineMetrics) -> str:
    return json.dumps(metrics_snapshot(metrics), sort_keys=True)


def metrics_prometheus(pipeline_name: str, metrics: PipelineMetrics) -> str:
    label = pipeline_name.replace("\\", "\\\\").replace('"', '\\"')
    lines = [
        "# HELP pipeworks_pipeline_metric Pipeline runtime metric.",
        "# TYPE pipeworks_pipeline_metric gauge",
    ]
    for name, value in metrics_snapshot(metrics).items():
        lines.append(f'pipeworks_{name}{{pipeline="{label}"}} {value}')
    return "\n".join(lines) + "\n"


def health_status(pipeline_name: str, state: PipelineState) -> HealthStatus:
    if state == PipelineState.ERROR:
        return HealthStatus(pipeline_name, state.value, "unhealthy", False, {"error": True})
    if state in {PipelineState.RUNNING, PipelineState.STOPPED}:
        return HealthStatus(pipeline_name, state.value, "healthy", True, {})
    return HealthStatus(pipeline_name, state.value, "starting", False, {})
