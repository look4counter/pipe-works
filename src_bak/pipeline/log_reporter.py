"""Best-effort pipeline log forwarding isolated from media processing."""

from __future__ import annotations

import json
import logging
import os
import queue
import threading
from urllib.parse import urlencode

from websockets.sync.client import connect

LOG_QUEUE_SIZE = 2048
RECONNECT_INTERVAL_SECONDS = 2.0
DEFAULT_LOG_WEBSOCKET_URL = "ws://127.0.0.1:{port}/ws/pipeline-logs"


class PipelineLogHandler(logging.Handler):
    """Put log records in a bounded queue without waiting on network I/O."""

    def __init__(self, events: queue.Queue[logging.LogRecord]) -> None:
        super().__init__()
        self.events = events

    def emit(self, record: logging.LogRecord) -> None:
        if record.name.startswith("pipeline.log_reporter"):
            return
        try:
            try:
                self.events.put_nowait(record)
            except queue.Full:
                # Keep the newest messages while ensuring a slow/disconnected
                # Conductor can never block a pipeline logging call.
                try:
                    self.events.get_nowait()
                    self.events.task_done()
                except queue.Empty:
                    pass
                try:
                    self.events.put_nowait(record)
                except queue.Full:
                    pass
        except Exception:
            self.handleError(record)


def _send_log_events(
    process_id: str,
    events: queue.Queue[logging.LogRecord],
    stop_event: threading.Event,
) -> None:
    port = os.environ.get("PIPE_WORKS_CONDUCTOR_PORT", "8000")
    base_url = os.environ.get(
        "PIPE_WORKS_LOGS_WS_URL", DEFAULT_LOG_WEBSOCKET_URL.format(port=port)
    )
    separator = "&" if "?" in base_url else "?"
    url = f"{base_url}{separator}{urlencode({'process_id': process_id})}"
    while True:
        if stop_event.is_set() and events.empty():
            return
        try:
            with connect(
                url,
                open_timeout=2,
                close_timeout=1,
                ping_interval=20,
                ping_timeout=5,
                proxy=None,
            ) as websocket:
                while True:
                    if stop_event.is_set() and events.empty():
                        return
                    try:
                        record = events.get(timeout=0.5)
                    except queue.Empty:
                        continue
                    try:
                        event = _serialize_record(process_id, record)
                    except Exception:
                        events.task_done()
                        continue
                    try:
                        websocket.send(json.dumps(event, separators=(",", ":")))
                    except Exception:
                        try:
                            events.put_nowait(record)
                        except queue.Full:
                            pass
                        raise
                    finally:
                        events.task_done()
        except Exception:
            if stop_event.is_set():
                return
            stop_event.wait(RECONNECT_INTERVAL_SECONDS)


def _serialize_record(process_id: str, record: logging.LogRecord) -> dict[str, object]:
    exception = (
        logging.Formatter().formatException(record.exc_info)
        if record.exc_info
        else None
    )
    return {
        "process_id": process_id,
        "created_at": record.created,
        "level": record.levelname[:32],
        "logger": record.name[:256],
        "message": record.getMessage()[:16000],
        "exception": exception[:32000] if exception else None,
    }


def start_log_reporting(
    process_id: str,
) -> tuple[threading.Event, threading.Thread, PipelineLogHandler]:
    """Attach a non-blocking handler and start its dedicated WebSocket thread."""
    events: queue.Queue[logging.LogRecord] = queue.Queue(maxsize=LOG_QUEUE_SIZE)
    stop_event = threading.Event()
    handler = PipelineLogHandler(events)
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)

    thread = threading.Thread(
        target=_send_log_events,
        args=(process_id, events, stop_event),
        name="pipeline-log-reporter",
        daemon=True,
    )
    thread.start()
    return stop_event, thread, handler


def stop_log_reporting(
    stop_event: threading.Event,
    thread: threading.Thread,
    handler: PipelineLogHandler,
) -> None:
    stop_event.set()
    thread.join(timeout=2.0)
    root_logger = logging.getLogger()
    root_logger.removeHandler(handler)
    handler.close()
