# Pipe Works

Pipe Works는 **Python 기반 실시간 영상 처리 Pipeline SDK**다. 목표는 단순히 RTSP 수신, AI 추론, Overlay, RTSP Publish 기능을 모아둔 라이브러리가 아니다.

핵심 목표는 다음과 같다.

> 개발자가 복잡한 영상 처리 내부 구현을 몰라도, 실제 영상 처리 흐름을 읽는 것처럼 직관적인 Python 코드로 Pipeline을 선언할 수 있어야 한다.

즉 `pipeline.py` 자체가 실행 가능한 아키텍처 다이어그램 역할을 해야 한다.

기존 구현은 삭제하지 않고 보존했다.

- 기존 `src` -> `src_bak`
- 기존 `specs` -> `specs_bak`

## 현재 상태

현재는 Public Pipeline DSL과 deterministic MVP runtime의 1차 구현이 들어가 있다.

구현된 항목:

- 읽기 쉬운 fluent Pipeline DSL
- `Pipeline.diagram()` 텍스트 다이어그램
- mock/descriptor 기반 단일 스트림 실행
- multi-stream batch inference 선언
- stream identity 보존
- multi-stage inference 결과 저장
- YAML 기반 동작 설정 override
- async action dispatch
- custom processor 삽입
- realtime queue/drop policy
- batch collection policy
- pipeline lifecycle state
- runtime metrics
- GStreamer RTSP, YOLO/TensorRT, HTTP, MQ, MediaMTX adapter boundary
- curated examples 7개
- `pipeworks --check`
- `pipeworks --init-example <DIR>`

## Pipeline DSL 예시

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

pipeline.run()
```

이 코드를 보면 다음 흐름을 바로 읽을 수 있어야 한다.

```text
RTSP 입력
  |
AI 추론
  +-- SVG 전송
  +-- MQ 발행
  |
정적 Overlay
  |
Detection Overlay
  |
RTSP 출력
```

## 실행과 검증

이 환경에서는 `uv`가 PATH에 없을 수 있으므로 기본적으로 `python -m ...` 명령을 사용한다.

```powershell
$env:PYTHONPATH='src'; python -m pytest -q
python -m ruff check src\pipeworks tests\sdk examples\01_single_stream_rtsp_style.py examples\02_multistream_batch.py examples\03_multistage_inference.py examples\04_custom_component.py examples\05_local_synthetic_config.py examples\06_observability_server.py examples\07_custom_source.py
$env:PYTHONPATH='src'; python -m pipeworks.cli --check
```

현재 기준:

- `pytest`: 41 passed
- `ruff`: All checks passed
- `pipeworks --check`: PASS

## 개발자 예제

개발자가 SDK를 어떻게 써야 하는지 보여주는 curated examples는 [examples](examples)에 있다.

- [01_single_stream_rtsp_style.py](examples/01_single_stream_rtsp_style.py): RTSP 형태의 단일 스트림 Pipeline
- [02_multistream_batch.py](examples/02_multistream_batch.py): 9채널 batch inference 선언
- [03_multistage_inference.py](examples/03_multistage_inference.py): 1차 모델 -> crop -> 2차 모델
- [04_custom_component.py](examples/04_custom_component.py): custom domain processor
- [05_local_synthetic_config.py](examples/05_local_synthetic_config.py): local synthetic source + YAML 설정 override
- [07_custom_source.py](examples/07_custom_source.py): custom finite/live Source 연결

예제들은 테스트에서 subprocess로 실제 실행된다. 예제가 깨지면 SDK 품질 게이트가 실패해야 한다.

## Starter 생성

새 Pipeline 프로젝트의 시작점을 만들 수 있다.

```powershell
$env:PYTHONPATH='src'; python -m pipeworks.cli --init-example ./my-pipeline
```

생성 파일:

- `pipeline.py`
- `pipeworks.yaml`

## 구조

- `src/pipeworks/pipeline.py`: fluent Pipeline DSL과 MVP runtime
- `src/pipeworks/components.py`: component protocol과 기본 MVP component
- `src/pipeworks/models.py`: `Frame`, `PipelineContext`, `DetectionResult`, metrics
- `src/pipeworks/runtime.py`: realtime queue/drop policy, batch collector
- `src/pipeworks/lifecycle.py`: pipeline lifecycle state
- `src/pipeworks/config.py`: default config와 YAML override
- `src/pipeworks/adapters`: optional runtime adapter boundary
- `src/pipeworks/harness`: command-backed quality gate
- `src/pipeworks/loop`: AI Agent LOOP foundation
- `examples`: 개발자용 SDK 사용 예제
- `docs`: 설계 문서와 ADR
- `specs`: 기능별 명세/작업 산출물

## 문서

- [제품 비전](docs/product-vision.md)
- [Pipeline SDK 설계](docs/pipeline-sdk-design.md)
- [아키텍처](docs/architecture.md)
- [LOOP 프로토콜](docs/loop-protocol.md)
- [품질 게이트](docs/quality-gates.md)
- [ADR](docs/adr)
- [AI Agent 인계 문서](AGENTS.md)

## 다음 개발 방향

다음 AI Agent는 [AGENTS.md](AGENTS.md)를 먼저 읽고 이어서 개발한다.

우선순위 높은 다음 작업:

1. `Pipeline.compile()`과 `PipelinePlan`
2. worker runtime skeleton
3. pipeline validation
4. GStreamer appsink 실제 frame extraction
5. Ultralytics/TensorRT 실제 adapter 구현
6. MediaMTX publish contract 구체화
7. metrics/health exporter
