# Pipe Works Agent Handoff

이 문서는 Codex, Claude, GitHub Copilot 등 어떤 AI Agent가 들어와도 같은 방향으로 이어서 개발하기 위한 단일 기준 문서다. 다른 에이전트별 지침 파일은 이 문서를 먼저 읽도록 연결한다.

## 프로젝트 정체성

Pipe Works는 **Python 기반 실시간 영상 처리 Pipeline SDK**다.

핵심 철학:

> 영상 처리 프로그램을 작성하는 것이 아니라, 영상 처리 Pipeline을 선언한다.

SDK 사용자는 `pipeline.py` 하나만 열어도 10초 안에 다음을 이해할 수 있어야 한다.

- 영상이 어디서 들어오는가
- 어떤 모델/처리를 거치는가
- 어떤 overlay/action을 수행하는가
- 어디로 출력되는가

따라서 Public API/DSL의 직관성이 내부 구현 편의보다 우선한다.

## 핵심 사용자 경험 규칙

Python DSL은 **What**을 표현한다.

- source URL
- stream id
- model path
- action target
- output target
- inference / batch inference / transform / overlay / action / output 순서

YAML configuration은 **How**를 표현한다.

- timeout
- retry
- reconnect
- confidence
- device
- fp16
- codec / bitrate
- queue size
- drop policy
- batch timeout
- performance tuning

Python 코드가 `config.xxx`로 도배되어 pipeline 의미를 숨기면 안 된다.

## 현재 저장소 상태

기존 구현은 보존되어 있다.

- old `src` -> `src_bak`
- old `specs` -> `specs_bak`

현재 SDK 구현 위치:

- `src/pipeworks/pipeline.py`: fluent Pipeline DSL and MVP runtime
- `src/pipeworks/plan.py`: compiled `PipelinePlan` execution shape
- `src/pipeworks/workers.py`: deterministic Source/Inference/Action/Output workers
- `src/pipeworks/validation.py`: early declaration validation and warnings
- `src/pipeworks/observability.py`: health, JSON, and Prometheus exporters
- `src/pipeworks/observability_server.py`: standard-library `/health` and `/metrics` HTTP adapter
- `src/pipeworks/components.py`: bounded async Action Dispatcher and graceful close
- `src/pipeworks/components.py`: public component protocols and MVP components
- `src/pipeworks/models.py`: `Frame`, `PipelineContext`, `DetectionResult`, metrics
- `src/pipeworks/runtime.py`: realtime queue/drop policies and batch collector
- `src/pipeworks/lifecycle.py`: pipeline lifecycle state model
- `src/pipeworks/config.py`: default config and YAML override loading
- `src/pipeworks/adapters/`: optional real-runtime adapter boundaries
- `src/pipeworks/harness/`: command-backed quality gates
- `src/pipeworks/loop/`: agent loop foundation

Developer-facing examples:

- `examples/01_single_stream_rtsp_style.py`
- `examples/02_multistream_batch.py`
- `examples/03_multistage_inference.py`
- `examples/04_custom_component.py`
- `examples/05_local_synthetic_config.py`

Design docs:

- `docs/product-vision.md`
- `docs/pipeline-sdk-design.md`
- `docs/architecture.md`
- `docs/adr/*.md`

Feature specs:

- `specs/002-pipeline-dsl-sdk`
- `specs/003-realtime-runtime-policies`
- `specs/004-command-harness-gates`
- `specs/005-pipeline-lifecycle`
- `specs/006-runtime-metrics`
- `specs/007-developer-examples-and-test-sources`
- `specs/008-gstreamer-rtsp-adapter`
- `specs/009-inference-adapter-boundary`
- `specs/010-output-action-adapters`
- `specs/011-http-action-reliability`
- `specs/012-examples-execution-harness`
- `specs/013-quality-check-cli`
- `specs/014-pipeline-diagram`
- `specs/015-init-example-cli`

## 지금까지 구현된 내용

Implemented and pushed to `main`:

- readable fluent Pipeline DSL
- `Pipeline.diagram()` text architecture diagram
- single-stream MVP runtime
- multi-stream `.streams([...])`
- explicit `.batch_inference(...)`
- stream identity preservation
- multi-stage inference results by stage
- custom `.process(...)` components
- `FrameQueue`, drop policies, queue metrics
- `BatchCollector`, `BatchPolicy`
- async action dispatcher
- lifecycle states: `created`, `starting`, `running`, `draining`, `stopped`, `error`, `reconnecting`
- runtime metrics: duration, effective FPS, queue drops/depth, batch size, action latency
- `SyntheticSource`, `FileSource`, RTSP descriptor source
- optional GStreamer RTSP adapter boundary
- optional Ultralytics/TensorRT inference adapter boundaries
- HTTP/MQ/MediaMTX action/output adapter boundaries
- real local HTTP action delivery and retry tests
- curated examples execution harness
- `pipeworks --check`
- `pipeworks --init-example <DIR>`
- optional package extras: `gstreamer`, `yolo`, `mq`, `all`
- wheel build verified on Python 3.14
- bounded Action queue with dropped-action metrics
- Source reconnect policy with configurable attempts and interval
- opt-in per-context failure isolation with `Pipeline.isolate_errors`
- batch inference adapter contracts with stream identity validation
- HTTP health/Prometheus endpoint example and Docker Compose deployment template
- GStreamer lazy `appsink` frame extraction and continuous source iterator contract
- `Pipeline.run_streams()` continuous multi-stream cycles with batch identity preservation
- bounded Context Queue between Worker stages with configurable drop policy
- lazy Ultralytics inference normalization and GPU retry policy
- TensorRT batch runner contract with retry and stream validation

Latest relevant commits:

- `67e416f feat: add starter example cli`
- `3e4f622 feat: add pipeline text diagram`
- `7155863 feat: add quality check cli`
- `10908a9 test: execute curated sdk examples`
- `ff07d9e feat: add http action reliability tests`
- `531d030 feat: add output and action adapter boundaries`
- `4e0cf1b feat: add inference adapter boundaries`
- `9c54c3e feat: add gstreamer rtsp adapter boundary`

## 에이전트 필수 작업 흐름

Human gate를 최소화한다. 명확한 blocker가 없으면 다음 순서로 계속 진행한다.

1. 작은 vertical slice를 고른다.
2. `specs/NNN-feature-name`에 spec/checklist/tasks를 남긴다.
3. 구현한다.
4. 테스트와 lint를 실행한다.
5. 커밋한다.
6. `git push origin main` 한다.
7. 다음 slice로 넘어간다.

작업 중 매번 사용자에게 허락을 묻지 않는다. 다음 경우에만 멈춘다.

- credential/account/external secret 필요
- destructive operation 필요
- production 영향이 있는 작업
- acceptance criteria가 서로 모순
- 로컬 도구로 evidence 생성 불가
- 같은 blocker가 3회 이상 반복

## 필수 검증

기본 검증 명령:

```powershell
$env:PYTHONPATH='src'; python -m pytest -q
python -m ruff check src\pipeworks tests\sdk examples\01_single_stream_rtsp_style.py examples\02_multistream_batch.py examples\03_multistage_inference.py examples\04_custom_component.py examples\05_local_synthetic_config.py
$env:PYTHONPATH='src'; python -m pipeworks.cli --check
```

현재 기준 통과 상태:

- `pytest`: 41 passed
- `ruff`: All checks passed
- `pipeworks --check`: PASS

주의:

- 이 환경에서는 `uv`가 PATH에 없을 수 있다. `python -m ...` 명령을 우선 사용한다.
- 옛 테스트/예제는 `src_bak` 이전 구현을 참조할 수 있으므로 기본 검증 범위는 `tests/sdk`와 curated examples다.

## Public API 예시

Single stream:

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

Multi-stream batch:

```python
pipeline = (
    Pipeline("cobble-9ch")
    .streams([
        Stream("cam01", source="rtsp://cam01", output="rtsp://out/cam01"),
        Stream("cam02", source="rtsp://cam02", output="rtsp://out/cam02"),
    ])
    .batch_inference(YoloInference("models/cobble.engine"))
    .overlay(DetectionBoxOverlay())
)
```

Do not make the normal user write:

- OpenCV loops
- GStreamer pipeline internals
- FFmpeg process management
- CUDA/TensorRT context management
- thread/process/queue/lock code
- batch collector / demux code
- reconnect loop
- encoder lifecycle

## 다음 권장 Slice

Continue in this order unless blocked:

1. Real adapter deepening
   - Ultralytics adapter real inference when dependency exists
   - TensorRT adapter execution skeleton when dependency exists
   - MediaMTX publish contract
2. Production runtime expansion
   - real TensorRT engine/session loader behind the batch runner contract
   - GPU batch scheduling metrics and CUDA recovery hooks
3. End-to-end operations
   - RTSP to MediaMTX integration tests
   - container image variants for GPU and GStreamer
   - deployment Secret and configuration examples

## 커밋 규칙

- Slice 단위로 커밋한다.
- 커밋 메시지는 `feat:`, `test:`, `docs:`, `fix:` prefix를 사용한다.
- 검증 통과 후 `git push origin main`까지 한다.
- 작업 트리를 깨끗하게 유지한다.

## 스타일 원칙

- Public DSL readability is more important than internal convenience.
- Keep runtime internals behind adapters/runtime modules.
- Prefer deterministic tests that run without RTSP, GPU, brokers, or external services.
- Add real integration only when it can gracefully skip or clearly report missing dependencies.
- Curated examples are part of the SDK contract; keep them executable.
