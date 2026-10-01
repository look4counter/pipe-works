"""Run a local pipeline with HTTP health and Prometheus endpoints."""

from __future__ import annotations

import argparse
import time

from pipeworks import (
    DetectionBoxOverlay,
    ObservabilityServer,
    Pipeline,
    SyntheticSource,
    YoloInference,
)


def build_pipeline() -> Pipeline:
    return (
        Pipeline("observability-demo")
        .source(SyntheticSource("local-cam", frame_count=3, width=320, height=180))
        .inference(YoloInference("models/local.engine"))
        .overlay(DetectionBoxOverlay())
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    pipeline = build_pipeline()
    result = pipeline.run()
    print(result.metrics.to_json())
    if args.once:
        return 0

    server = ObservabilityServer(pipeline, host=args.host, port=args.port).start()
    print(f"health=http://{args.host}:{server.address[1]}/health")
    print(f"metrics=http://{args.host}:{server.address[1]}/metrics")
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        return 0
    finally:
        server.stop()


if __name__ == "__main__":
    raise SystemExit(main())
