"""Process-local pipeline counters, isolated from media operations."""

from __future__ import annotations

import math
from threading import Lock


STATISTIC_FIELDS = (
    "received",
    "sent",
    "anomalous",
    "inferenceFailed",
    "postprocessFailed",
)


class PipelineStatistics:
    def __init__(self) -> None:
        self._lock = Lock()
        self._values = {field: 0 for field in STATISTIC_FIELDS}
        self._values["average_ms"] = None
        self._last_decoded_pts: int | None = None

    def increment(self, field: str) -> None:
        with self._lock:
            self._values[field] += 1

    def set_average_ms(self, value: float) -> None:
        if not math.isfinite(value) or value < 0:
            return
        with self._lock:
            self._values["average_ms"] = value

    def observe_decoded_pts(self, pts: int | None) -> bool:
        if pts is None:
            return False
        with self._lock:
            anomalous = (
                self._last_decoded_pts is not None
                and pts <= self._last_decoded_pts
            )
            if anomalous:
                self._values["anomalous"] += 1
            self._last_decoded_pts = pts
            return anomalous

    def reset_decode_order(self) -> None:
        with self._lock:
            self._last_decoded_pts = None

    def reset(self) -> None:
        with self._lock:
            for field in STATISTIC_FIELDS:
                self._values[field] = 0
            self._values["average_ms"] = None
            self._last_decoded_pts = None

    def snapshot(self) -> dict[str, int | float | None]:
        with self._lock:
            return self._values.copy()


PIPELINE_STATISTICS = PipelineStatistics()
