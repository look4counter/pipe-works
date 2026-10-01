"""External action adapter boundaries."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from importlib.util import find_spec
from urllib import error, request

from pipeworks.models import PipelineContext


class ActionAdapterUnavailableError(RuntimeError):
    """Raised when an action adapter cannot run in the current environment."""


@dataclass
class HttpPostAction:
    url: str
    name: str = "HttpPostAction"

    def build_payload(self, context: PipelineContext) -> dict[str, object]:
        return {
            "stream_id": context.stream_id,
            "sequence": context.frame.sequence,
            "detections": [
                {
                    "box": detection.box,
                    "confidence": detection.confidence,
                    "class_id": detection.class_id,
                    "label": detection.label,
                }
                for detection in context.detections
            ],
        }

    def execute(self, context: PipelineContext, settings: dict[str, object]) -> None:
        timeout = float(settings.get("timeout", 3))
        retry = int(settings.get("retry", 0))
        payload = json.dumps(self.build_payload(context)).encode("utf-8")
        last_error: Exception | None = None
        for _attempt in range(retry + 1):
            req = request.Request(
                self.url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with request.urlopen(req, timeout=timeout):
                    return
            except (OSError, error.HTTPError, error.URLError) as exc:
                last_error = exc
        if last_error is not None:
            raise last_error


def is_pika_available() -> bool:
    return find_spec("pika") is not None


@dataclass
class MQAdapterAction:
    topic: str
    broker_url: str = "amqp://guest:guest@localhost:5672/"
    name: str = "MQAdapterAction"
    publisher: Callable[[str, dict[str, object]], None] | None = None

    @property
    def available(self) -> bool:
        return is_pika_available()

    def build_message(self, context: PipelineContext) -> dict[str, object]:
        return {
            "topic": self.topic,
            "stream_id": context.stream_id,
            "sequence": context.frame.sequence,
            "detections": len(context.detections),
        }

    def execute(self, context: PipelineContext, settings: dict[str, object]) -> None:
        if self.publisher is not None:
            self.publisher(self.topic, self.build_message(context))
            return
        if not self.available:
            raise ActionAdapterUnavailableError(
                "MQAdapterAction requires the 'pika' package and a reachable AMQP broker. "
                "Install the mq extra or use MQPublishAction for local tests."
            )
        raise NotImplementedError("Real MQ publishing is scheduled for the broker adapter slice.")
