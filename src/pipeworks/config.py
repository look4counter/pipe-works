"""Runtime configuration loading and component override helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG: dict[str, dict[str, Any]] = {
    "Pipeline": {
        "queue_size": 8,
        "drop_policy": "latest",
        "worker_queue_size": 64,
        "worker_drop_policy": "latest",
        "isolate_errors": False,
    },
    "BatchInference": {"max_batch_size": 16, "max_wait_ms": 20, "drop_policy": "latest"},
    "RTSPSource": {
        "reconnect": True,
        "reconnect_attempts": 3,
        "reconnect_interval": 3,
        "timeout": 10,
    },
    "YoloInference": {"confidence": 0.5, "device": "cpu", "fp16": False},
    "Action": {"timeout": 3, "retry": 0, "max_workers": 4, "max_pending": 64},
    "RTSPPublisher": {"codec": "h264", "fps": 25, "bitrate": "4M"},
}


@dataclass(frozen=True)
class RuntimeConfig:
    """Merged runtime configuration.

    Sections are keyed by component class name or explicit component name.
    """

    sections: dict[str, dict[str, Any]] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()

    @classmethod
    def defaults(cls) -> RuntimeConfig:
        return cls(sections={key: dict(value) for key, value in DEFAULT_CONFIG.items()})

    @classmethod
    def from_yaml(cls, path: str | Path | None) -> RuntimeConfig:
        base = cls.defaults()
        if path is None:
            return base

        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raise TypeError("runtime config YAML root must be a mapping")

        sections = {key: dict(value) for key, value in base.sections.items()}
        warnings: list[str] = []
        for key, value in raw.items():
            if not isinstance(value, dict):
                warnings.append(f"ignored non-mapping config section {key!r}")
                continue
            current = sections.setdefault(str(key), {})
            current.update(value)
        return cls(sections=sections, warnings=tuple(warnings))

    def for_component(self, component: object, fallback: str | None = None) -> dict[str, Any]:
        component_type = component.__class__.__name__
        merged: dict[str, Any] = {}
        if fallback and fallback in self.sections:
            merged.update(self.sections[fallback])
        if component_type in self.sections:
            merged.update(self.sections[component_type])
        component_name = getattr(component, "name", None)
        if component_name and component_name in self.sections:
            merged.update(self.sections[component_name])
        return merged
