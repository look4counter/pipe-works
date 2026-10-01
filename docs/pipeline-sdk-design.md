# Pipeline SDK 설계

## 1. Developer Experience 원칙

SDK 사용자는 영상 처리 프로그램을 작성하는 것이 아니라, 영상 처리 Pipeline을 선언한다.

`pipeline.py`는 실행 가능한 아키텍처 다이어그램이어야 한다. 입력, 모델, overlay, action, output이 fluent call chain만 보고 드러나야 한다.

원칙:

- Python DSL은 **무엇을 연결하는가**를 표현한다.
- YAML은 **어떻게 동작하는가**를 표현한다.
- YAML이 없어도 합리적인 기본값으로 실행된다.
- Batch inference는 실행 의미가 달라지므로 DSL에 명시한다.
- Runtime 내부 구현은 일반 사용자에게 숨긴다.
- Custom component는 자연스럽게 chain에 삽입된다.

## 2. 대표 Use Case

- 단일 RTSP stream -> inference -> overlay -> MQ/HTTP action -> RTSP output
- 9개 camera stream -> shared batch inference -> stream별 overlay/output
- 1차 model -> crop/transform -> 2차 model -> overlay/output
- 현장별 custom filter/processor 삽입

## 3. Public API / DSL

```python
pipeline = (
    Pipeline("cobble-detection")
    .source(RTSPSource("rtsp://camera/main"))
    .inference(YoloInference("models/cobble.engine"))
    .overlay(StaticBoxOverlay())
    .overlay(DetectionBoxOverlay())
    .action(SvgSendAction("http://server/api/svg"))
    .action(MQPublishAction("cobble.detected"))
    .output(RTSPPublisher("rtsp://mediamtx/cobble"))
)
```

## 4. Single Stream 예제

[01_single_stream_rtsp_style.py](../examples/01_single_stream_rtsp_style.py)를 본다.

## 5. Multi Stream 예제

[02_multistream_batch.py](../examples/02_multistream_batch.py)를 본다.

## 6. Batch Inference 예제

Batch inference는 YAML에 숨기지 않고 `.batch_inference(...)`로 선언한다. Runtime은 frame collection, batch inference 호출, result mapping을 책임진다.

## 7. Multi Stage Inference 예제

[03_multistage_inference.py](../examples/03_multistage_inference.py)를 본다. `primary`, `secondary` 같은 stage 이름은 `PipelineContext.results`에 보존된다.

## 8. Custom Component 확장

[04_custom_component.py](../examples/04_custom_component.py)를 본다. Custom component는 `process(context) -> context`를 구현하고 `.process(...)`로 삽입한다.

## 9. Runtime Architecture

Fluent declaration은 ordered step으로 컴파일된다. Runtime의 기본 단위는 `PipelineContext`다.

`PipelineContext`는 다음을 가진다.

- stream-aware `Frame`
- inference result
- overlay command
- event/action 정보
- error
- scratch data

MVP runtime:

```text
Source/Streams -> Contexts -> Ordered Steps -> Outputs
                              -> Actions via dispatcher
```

향후 worker runtime:

```text
Source workers -> bounded frame queues -> batch collector -> inference worker
 -> demultiplexer -> per-stream processors -> output workers
```

## 10. Component Interface

현재 MVP protocol:

- `SourceComponent.frames()`
- `InferenceComponent.infer(context, settings)`
- `BatchInferenceComponent.infer_batch(contexts, settings)`
- `ProcessorComponent.process(context)`
- `OverlayComponent.apply(context)`
- `ActionComponent.execute(context, settings)`
- `OutputComponent.write(context, settings)`

깊은 inheritance tree 대신 structural protocol을 선택했다. 사용자는 SDK base class에 강하게 묶이지 않고 평범한 Python object로 확장할 수 있다.

## 11. Frame / Context / Result Model

- `Frame`: `stream_id`, `image`, `timestamp`, `sequence`, metadata
- `PipelineContext`: frame, stage result, overlay, event, error, scratch data
- `DetectionResult`: `stream_id`, `stage`, detection list, frame sequence

Stream identity는 side table이 아니라 데이터 모델 자체에 포함한다.

## 12. Concurrency / Async / Queue Architecture

MVP는 main path를 deterministic하게 유지하고 action은 background dispatcher로 보낸다.

향후 slice에서 source, inference, action, output 사이에 bounded queue를 둔 worker runtime을 추가한다.

## 13. GPU / TensorRT 실행 모델

GPU 실행은 후속 adapter에서 담당한다. Public contract는 이미 준비되어 있다.

- Python: `YoloInference("models/cobble.engine")`
- YAML: device, fp16, confidence, max batch size, batch wait

## 14. Backpressure / Frame Drop / Batch 전략

기본값은 backlog 누적보다 real-time freshness를 우선한다.

- queue size는 bounded
- 기본 drop policy는 `latest`
- batch inference는 `max_batch_size`, `max_wait_ms`를 가진다
- 느린 stream이 정상 stream을 무기한 막으면 안 된다

## 15. Configuration 구조

```yaml
YoloInference:
  confidence: 0.7
  device: cuda:0
  fp16: true

BatchInference:
  max_batch_size: 9
  max_wait_ms: 20
  drop_policy: latest
```

Python constructor에는 URL, model path, topic, output target 같은 identity 값이 남는다.

## 16. Error Handling / Reconnect / Lifecycle

MVP는 context와 metrics에 error를 기록한다. Lifecycle state는 다음을 지원한다.

- `created`
- `starting`
- `running`
- `draining`
- `stopped`
- `error`
- `reconnecting`

## 17. Logging / Metrics / Observability

현재 metrics:

- processed frame count
- action count
- output count
- queue dropped count
- queue max depth
- batch size
- duration
- effective FPS
- action latency
- error count

향후 추가:

- latency percentile
- reconnect attempts
- GPU/VRAM
- Prometheus exporter
- health snapshot

## 18. Test 전략

현재 테스트가 검증하는 것:

- DSL readability
- YAML override
- stream identity preservation
- multi-stage inference result
- custom component
- non-blocking action
- queue/drop policy
- lifecycle
- metrics
- HTTP action retry
- curated examples execution
- `pipeworks --check`
- `pipeworks --init-example`

## 19. Package 구조

- `pipeworks.pipeline`: fluent DSL and MVP runtime
- `pipeworks.models`: public data models
- `pipeworks.components`: protocol and built-in MVP components
- `pipeworks.config`: defaults and YAML override
- `pipeworks.runtime`: queue/drop/batch policy
- `pipeworks.lifecycle`: lifecycle state
- `pipeworks.adapters`: optional runtime adapter boundary
- `pipeworks.loop` / `pipeworks.harness`: AI Agent engineering support layer

## 20. MVP 구현 상태

MVP는 deterministic mock/local execution 기반이다. 실제 RTSP, GPU, broker, MediaMTX adapter는 Public DSL을 유지하면서 점진적으로 깊어진다.

## 현재 완료된 Autonomous Slices

- Pipeline DSL MVP
- Realtime queue/drop policy
- Command-backed harness gate
- Pipeline lifecycle model
- Runtime metrics
- Local synthetic/file source
- 개발자용 curated examples
- GStreamer RTSP adapter boundary
- YOLO/TensorRT inference adapter boundary
- HTTP/MQ/MediaMTX action/output adapter boundary
- HTTP action reliability
- examples execution harness
- quality check CLI
- text diagram
- starter example CLI
