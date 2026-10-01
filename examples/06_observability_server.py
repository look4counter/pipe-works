"""예제 06: Pipeline을 실행하고 Health/Prometheus Endpoint를 연다.

로컬 확인은 ``--once``를 사용하고, 컨테이너나 운영 환경에서는 기본 모드로
실행해 ``/health``와 ``/metrics``를 readiness/scrape 대상에 사용한다.
"""

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
    """운영 환경에서는 이 함수만 실제 Pipeline으로 교체한다."""

    return (
        Pipeline("observability-demo")
        .source(SyntheticSource("local-cam", frame_count=3, width=320, height=180))
        .inference(YoloInference("models/local.engine"))
        .overlay(DetectionBoxOverlay())
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Pipe Works 관찰성 Endpoint 예제")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    pipeline = build_pipeline()
    # Pipeline 실행이 끝난 뒤에도 마지막 메트릭을 Endpoint에서 제공한다.
    result = pipeline.run()
    print(result.metrics.to_json())
    if args.once:
        return 0

    server = ObservabilityServer(pipeline, host=args.host, port=args.port).start()
    print(f"Health: http://{args.host}:{server.address[1]}/health")
    print(f"Metrics: http://{args.host}:{server.address[1]}/metrics")
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        return 0
    finally:
        server.stop()


if __name__ == "__main__":
    raise SystemExit(main())
