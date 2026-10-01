# ADR-001: 런타임보다 Public DSL을 먼저 설계한다

## 상태

채택

## 배경

SDK의 핵심 품질 기준은 개발자가 pipeline.py를 열었을 때 영상 흐름을
이해할 수 있는지다. GStreamer, FFmpeg, TensorRT, 큐, 워커, 재연결 루프는
중요하지만 Public API의 모양을 결정해서는 안 된다.

## 결정

먼저 읽기 쉬운 fluent Pipeline DSL을 설계하고, 그 DSL을 만족하도록 런타임
내부를 설계한다. MVP는 source, streams, inference, batch_inference,
transform, process, overlay, action, output의 순서 있는 영상 개념을
노출한다.

## 검토한 대안

- 런타임 우선 API: 구현은 쉽지만 큐, 워커, demux 개념이 사용자 코드로 새어 나온다.
- YAML 우선 API: 운영 유연성은 높지만 소스, 모델, 출력의 정체성이 코드에서 사라진다.

## 결과

내부에는 어댑터와 컴파일러 계층이 필요할 수 있지만 사용자 코드는 읽기
쉬운 상태를 유지한다. 이후 런타임 최적화도 DSL의 명확성을 깨뜨리지 않아야 한다.
