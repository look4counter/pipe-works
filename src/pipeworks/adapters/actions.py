"""External action adapter boundaries."""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.util import find_spec
from urllib import request

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
        payload = json.dumps(self.build_payload(context)).encode("utf-8")
        req = request.Request(
            self.url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=timeout):
            return


def is_pika_available() -> bool:
    return find_spec("pika") is not None


@dataclass
class MQAdapterAction:
    topic: str
    broker_url: str = "amqp://guest:guest@localhost:5672/"
    name: str = "MQAdapterAction"

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
        if not self.available:
            raise ActionAdapterUnavailableError(
                "MQAdapterAction requires the 'pika' package and a reachable AMQP broker. "
                "Install the mq extra or use MQPublishAction for local tests."
            )
        raise NotImplementedError("Real MQ publishing is scheduled for the broker adapter slice.")
