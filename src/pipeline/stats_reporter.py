"""Best-effort WebSocket reporting, isolated on a dedicated thread."""

from __future__ import annotations

import json
import logging
import os
from threading import Event

from websockets.sync.client import connect

from pipeline.statistics import PIPELINE_STATISTICS

logger = logging.getLogger(__name__)
REPORT_INTERVAL_SECONDS = 0.25
RECONNECT_INTERVAL_SECONDS = 2.0
DEFAULT_STATS_WEBSOCKET_URL = "ws://127.0.0.1:{port}/ws/pipeline-stats"


def report_statistics(process_id: str, stop_event: Event) -> None:
    """Publish cumulative process counters; network waits never block the pipeline."""
    port = os.environ.get("PIPE_WORKS_CONDUCTOR_PORT", "8000")
    url = os.environ.get(
        "PIPE_WORKS_STATS_WS_URL", DEFAULT_STATS_WEBSOCKET_URL.format(port=port)
    )

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
                while True:
                    websocket.send(
                        json.dumps(
                            {
                                "process_id": process_id,
                                "statistics": PIPELINE_STATISTICS.snapshot(),
                            },
                            separators=(",", ":"),
                        )
                    )
                    if stop_event.wait(REPORT_INTERVAL_SECONDS):
                                # Send a final snapshot so a quick pipeline failure isn't
                                # lost just because the next reporting interval didn't pass.
                        websocket.send(
                            json.dumps(
                                {
                                    "process_id": process_id,
                                    "statistics": PIPELINE_STATISTICS.snapshot(),
                                },
                                separators=(",", ":"),
                            )
                        )
                        return
        except Exception:
            if stop_event.is_set():
                return
            logger.warning("통계 WebSocket 연결 실패, 재시도합니다: %s", url, exc_info=True)
            stop_event.wait(RECONNECT_INTERVAL_SECONDS)
