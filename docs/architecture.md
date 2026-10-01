# Pipe Works 아키텍처

Pipe Works는 AI Agent 기반 개발 루프를 활용해 만드는 **실시간 영상 Pipeline SDK**다. 제품 도메인은 media와 AI inference이며, LOOP engine과 harness는 SDK를 빠르게 구현하고 검증하기 위한 내부 엔지니어링 장치다.

참조 방향은 `C:\workspace\github\visionflow-sdk\docs`에서 가져왔다.

- GStreamer 스타일 media runtime boundary
- camera별 pipeline isolation
- bounded queue
- freshness-aware frame drop
- SDK 소유 metadata contract
- async event/action dispatch
- observability

## Product SDK

SDK는 다음 계약을 안정적으로 제공해야 한다.

- `Source`: RTSP, file, synthetic, mock source
- `Frame`: timestamp와 stream identity를 가진 image/video payload
- `FrameQueue`: `drop_oldest`, `drop_newest`, `block`, `latest` 정책을 가진 bounded queue
- `InferenceProvider`: local/remote model adapter
- `DetectionResult`: SDK 소유 정규화 metadata
- `Action`: HTTP/MQ/SVG 등 non-blocking side effect
- `Output`: RTSP/MediaMTX/file 등 output boundary
- `Pipeline`: lifecycle, failure isolation, graceful shutdown, metrics

## Engineering Layer

- `pipeworks.loop`: unblocked task 선택, agent adapter 실행, harness 호출
- `pipeworks.harness`: lint/test/contract/failure/performance gate
- `pipeworks.adapters`: agent, tool, CI, store, runtime adapter 연결

이 계층은 제품 SDK를 지원하기 위한 장치다. Public media SDK API를 가리면 안 된다.

## 채택 원칙

- Core SDK contract는 vendor-neutral로 유지한다.
- GStreamer, YOLO, TensorRT, broker, store는 adapter 뒤에 둔다.
- Media plane과 action/event plane을 분리한다.
- Queue, worker, retry, retained frame, event buffer는 bounded여야 한다.
- Real-time 동작은 backlog보다 freshness를 우선한다.
- Camera/plugin failure의 blast radius를 명확히 한다.
- Lifecycle state는 관측 가능해야 한다.
- Metadata는 model vendor 형식이 아니라 SDK 계약에 속한다.
- Observability는 부가 기능이 아니라 기본 동작이다.
- 완료된 agent loop는 evidence를 남긴다.
- Human gate는 irreversible/ambiguous decision에만 사용한다.

## 다음 주요 설계 결정

- `Pipeline.compile()`과 `PipelinePlan`
- Worker runtime skeleton
- 실제 GStreamer appsink frame extraction
- 실제 YOLO/TensorRT adapter
- MediaMTX publish contract
- Metrics/health exporter
