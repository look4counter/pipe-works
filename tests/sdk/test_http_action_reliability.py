from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from typing import ClassVar

from pipeworks import Frame, PipelineContext, YoloInference
from pipeworks.adapters.actions import HttpPostAction


class RecordingHandler(BaseHTTPRequestHandler):
    received: ClassVar[list[dict[str, object]]] = []
    status_codes: ClassVar[list[int]] = [200]

    def do_POST(self) -> None:
        length = int(self.headers["Content-Length"])
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        self.__class__.received.append(payload)
        status = self.__class__.status_codes.pop(0) if self.__class__.status_codes else 200
        self.send_response(status)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        return


def context_with_detection() -> PipelineContext:
    context = PipelineContext(Frame("cam01", sequence=42))
    context.add_result(YoloInference("models/fake.engine").infer(context, {"confidence": 0.9}))
    return context


def run_server(status_codes: list[int]) -> tuple[HTTPServer, str]:
    RecordingHandler.received = []
    RecordingHandler.status_codes = status_codes
    server = HTTPServer(("127.0.0.1", 0), RecordingHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, f"http://{host}:{port}/events"


def test_http_post_action_delivers_json_to_local_server() -> None:
    server, url = run_server([200])
    try:
        HttpPostAction(url).execute(context_with_detection(), {"timeout": 2})
    finally:
        server.shutdown()

    assert RecordingHandler.received[0]["stream_id"] == "cam01"
    assert RecordingHandler.received[0]["sequence"] == 42
    assert RecordingHandler.received[0]["detections"][0]["confidence"] == 0.9


def test_http_post_action_retries_transient_failure() -> None:
    server, url = run_server([500, 200])
    try:
        HttpPostAction(url).execute(context_with_detection(), {"timeout": 2, "retry": 1})
    finally:
        server.shutdown()

    assert len(RecordingHandler.received) == 2
