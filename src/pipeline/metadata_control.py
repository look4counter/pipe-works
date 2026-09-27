"""Receive metadata reload requests from the local Conductor service."""

from __future__ import annotations

import json
import logging
import os
from threading import Event, Thread
from urllib.parse import urlencode

from websockets.sync.client import connect

logger = logging.getLogger(__name__)
RECONNECT_INTERVAL_SECONDS = 2.0
DEFAULT_CONTROL_WEBSOCKET_URL = "ws://127.0.0.1:{port}/ws/pipeline-control"


def start_metadata_control(
    process_id: str, reload_event: Event
) -> tuple[Event, Thread]:
    stop_event = Event()
    thread = Thread(
        target=_receive_commands,
        args=(process_id, reload_event, stop_event),
        name="metadata-control-reporter",
        daemon=True,
    )
    thread.start()
    return stop_event, thread


def _receive_commands(
    process_id: str, reload_event: Event, stop_event: Event
) -> None:
    port = os.environ.get("PIPE_WORKS_CONDUCTOR_PORT", "8000")
    base_url = os.environ.get(
        "PIPE_WORKS_CONTROL_WS_URL",
        DEFAULT_CONTROL_WEBSOCKET_URL.format(port=port),
    )
    separator = "&" if "?" in base_url else "?"
    url = f"{base_url}{separator}{urlencode({'process_id': process_id})}"

    while not stop_event.is_set():
        try:
            with connect(
                url,
                open_timeout=2,
                close_timeout=1,
                ping_interval=20,
                ping_timeout=5,
                proxy=None,
            ) as websocket:
                while not stop_event.is_set():
                    try:
                        message = websocket.recv(timeout=0.5)
                    except TimeoutError:
                        continue
                    try:
                        command = json.loads(message)
                    except (TypeError, json.JSONDecodeError):
                        continue
                    if (
                        isinstance(command, dict)
                        and command.get("command") == "reload_metadata"
                    ):
                        reload_event.set()
        except Exception:
            if stop_event.is_set():
                return
            logger.warning(
                "Metadata control WebSocket connection failed; retrying: %s",
                url,
                exc_info=True,
            )
            stop_event.wait(RECONNECT_INTERVAL_SECONDS)
