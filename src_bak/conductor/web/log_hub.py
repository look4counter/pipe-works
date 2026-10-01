"""Bounded in-memory log history and per-process WebSocket fan-out."""

from __future__ import annotations

import asyncio
from collections import deque
from typing import Any

from fastapi import WebSocket
from fastapi.websockets import WebSocketDisconnect

MAX_LOG_HISTORY = 500
CLIENT_QUEUE_SIZE = 256


class LogHub:
    def __init__(self) -> None:
        self._history: dict[str, deque[dict[str, Any]]] = {}
        self._clients: dict[str, set[asyncio.Queue[dict[str, Any]]]] = {}

    def publish(self, process_id: str, event: dict[str, Any]) -> None:
        history = self._history.setdefault(
            process_id, deque(maxlen=MAX_LOG_HISTORY)
        )
        history.append(event)
        for queue in tuple(self._clients.get(process_id, ())):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass

    def remove_process(self, process_id: str) -> None:
        self._history.pop(process_id, None)

    async def stream_to_browser(self, websocket: WebSocket, process_id: str) -> None:
        await websocket.accept()
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(
            maxsize=CLIENT_QUEUE_SIZE
        )
        clients = self._clients.setdefault(process_id, set())
        clients.add(queue)
        try:
            await websocket.send_json(
                {
                    "process_id": process_id,
                    "events": list(self._history.get(process_id, ())),
                }
            )
            while True:
                await websocket.send_json(
                    {"process_id": process_id, "event": await queue.get()}
                )
        except WebSocketDisconnect:
            pass
        finally:
            clients.discard(queue)
            if not clients:
                self._clients.pop(process_id, None)

    @staticmethod
    def parse_update(message: object) -> tuple[str, dict[str, Any]] | None:
        if not isinstance(message, dict):
            return None
        process_id = message.get("process_id")
        if not isinstance(process_id, str) or not process_id.strip():
            return None
        created_at = message.get("created_at")
        level = message.get("level")
        logger_name = message.get("logger")
        text = message.get("message")
        exception = message.get("exception")
        if (
            not isinstance(created_at, (int, float))
            or not isinstance(level, str)
            or not isinstance(logger_name, str)
            or not isinstance(text, str)
            or (exception is not None and not isinstance(exception, str))
        ):
            return None
        return process_id, {
            "created_at": created_at,
            "level": level[:32],
            "logger": logger_name[:256],
            "message": text[:16000],
            "exception": exception[:32000] if exception else None,
        }
