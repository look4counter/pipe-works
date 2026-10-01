"""In-memory snapshots and non-blocking fan-out for pipeline statistics."""

from __future__ import annotations

import asyncio
import math
from typing import Any

from fastapi import WebSocket
from fastapi.websockets import WebSocketDisconnect

STATISTIC_FIELDS = (
    "received",
    "sent",
    "anomalous",
    "inferenceFailed",
    "postprocessFailed",
)


class StatisticsHub:
    def __init__(self) -> None:
        self.latest: dict[str, dict[str, Any]] = {}
        self._clients: set[asyncio.Queue[dict[str, Any]]] = set()

    def publish(
        self, process_id: str, values: dict[str, int | float | None]
    ) -> None:
        snapshot = {"process_id": process_id, "statistics": values}
        self.latest[process_id] = snapshot
        for queue in tuple(self._clients):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                queue.put_nowait(snapshot)
            except asyncio.QueueFull:
                pass

    async def stream_to_browser(self, websocket: WebSocket) -> None:
        await websocket.accept()
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=256)
        self._clients.add(queue)
        try:
            for snapshot in list(self.latest.values())[-queue.maxsize :]:
                queue.put_nowait(snapshot)
            while True:
                await websocket.send_json(await queue.get())
        except WebSocketDisconnect:
            pass
        finally:
            self._clients.discard(queue)

    @staticmethod
    def parse_update(
        message: object,
    ) -> tuple[str, dict[str, int | float | None]] | None:
        if not isinstance(message, dict):
            return None
        process_id = message.get("process_id")
        values = message.get("statistics")
        if not isinstance(process_id, str) or not process_id.strip():
            return None
        if not isinstance(values, dict):
            return None
        counters: dict[str, int | float | None] = {}
        for field in STATISTIC_FIELDS:
            value = values.get(field)
            if type(value) is not int or value < 0:
                return None
            counters[field] = value
        average_ms = values.get("average_ms")
        if average_ms is not None:
            if (
                isinstance(average_ms, bool)
                or not isinstance(average_ms, (int, float))
            ):
                return None
            try:
                average_ms = float(average_ms)
            except (OverflowError, ValueError):
                return None
            if not math.isfinite(average_ms) or average_ms < 0:
                return None
        counters["average_ms"] = average_ms
        return process_id, counters
