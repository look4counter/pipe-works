"""Small standard-library HTTP adapter for health and metrics endpoints."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import TYPE_CHECKING, Self

from pipeworks.models import PipelineMetrics
from pipeworks.observability import metrics_prometheus

if TYPE_CHECKING:
    from pipeworks.pipeline import Pipeline


class ObservabilityServer:
    """Serve `/health` and `/metrics` without adding a web framework dependency."""

    def __init__(self, pipeline: Pipeline, host: str = "127.0.0.1", port: int = 0) -> None:
        self.pipeline = pipeline
        self.host = host
        self.port = port
        self._server: ThreadingHTTPServer | None = None
        self._thread: Thread | None = None

    @property
    def address(self) -> tuple[str, int]:
        if self._server is None:
            return self.host, self.port
        return self._server.server_address

    def start(self) -> ObservabilityServer:
        if self._server is not None:
            return self

        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                if self.path == "/health":
                    self._send_json(200, owner.pipeline.health().to_dict())
                    return
                if self.path == "/metrics":
                    metrics = owner.pipeline.metrics or PipelineMetrics(0, 0, 0, 0, 0, 0)
                    payload = metrics_prometheus(owner.pipeline.name, metrics).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain; version=0.0.4")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                    return
                self._send_json(404, {"error": "not found"})

            def _send_json(self, status: int, value: dict[str, object]) -> None:
                payload = json.dumps(value, sort_keys=True).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, format: str, *args: object) -> None:
                return

        self._server = ThreadingHTTPServer((self.host, self.port), Handler)
        self._thread = Thread(target=self._server.serve_forever, name="pipeworks-observability")
        self._thread.daemon = True
        self._thread.start()
        return self

    def stop(self) -> None:
        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)
        self._server = None
        self._thread = None

    def __enter__(self) -> Self:
        return self.start()

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.stop()
