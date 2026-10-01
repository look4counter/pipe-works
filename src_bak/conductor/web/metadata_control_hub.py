"""Best-effort commands from Conductor to running pipeline processes."""

from __future__ import annotations

import asyncio

from fastapi import WebSocket
from fastapi.websockets import WebSocketDisconnect


class MetadataControlHub:
    def __init__(self) -> None:
        self._clients: dict[str, set[asyncio.Queue[dict[str, str]]]] = {}

    async def stream_to_pipeline(
        self, websocket: WebSocket, process_id: str
    ) -> None:
        await websocket.accept()
        queue: asyncio.Queue[dict[str, str]] = asyncio.Queue(maxsize=1)
        clients = self._clients.setdefault(process_id, set())
        clients.add(queue)

        async def send_commands() -> None:
            while True:
                await websocket.send_json(await queue.get())

        async def watch_disconnect() -> None:
            while True:
                message = await websocket.receive()
                if message["type"] == "websocket.disconnect":
                    return

        try:
            tasks = {
                asyncio.create_task(send_commands()),
                asyncio.create_task(watch_disconnect()),
            }
            done, pending = await asyncio.wait(
                tasks, return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            for task in done:
                try:
                    task.result()
                except (WebSocketDisconnect, RuntimeError):
                    pass
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            clients.discard(queue)
            if not clients:
                self._clients.pop(process_id, None)

    def request_metadata_reload(self, process_id: str) -> bool:
        clients = self._clients.get(process_id)
        if not clients:
            return False

        command = {"command": "reload_metadata"}
        for queue in tuple(clients):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                queue.put_nowait(command)
            except asyncio.QueueFull:
                pass
        return True
