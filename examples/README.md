# Pipe Works 예제 How-to

이 디렉터리는 Pipe Works SDK를 처음 사용하는 개발자가 **영상 흐름을 코드만
읽고 이해하는 방법**을 익히도록 만든 공식 예제 모음이다.

모든 공식 예제는 다음 원칙을 따른다.

- Python DSL에는 Source, Model, Transform, Overlay, Action, Output의 정체성을 적는다.
- timeout, retry, queue, confidence, device 같은 운영값은 YAML로 분리한다.
- OpenCV/GStreamer/Thread/Queue/Batch Demux 구현을 예제 코드에 직접 노출하지 않는다.
- 카메라, GPU, MQ가 없어도 기본 예제는 실행되어야 한다.
- 실제 운영으로 옮길 때 교체할 지점을 주석과 문서에 남긴다.

설정 파일은 `examples/config/`에 모아두었다. Python 파일에서 Pipeline의
의미를 읽고, YAML 파일에서 성능·재시도·큐·장치 같은 운영 튜닝값을 읽는다.

| 설정 파일 | 연결된 예제 | 용도 |
| --- | --- | --- |
| `config/single_stream.yaml` | `01_single_stream_rtsp_style.py` | 단일 RTSP/Action/Output 튜닝 |
| `config/multistream_batch.yaml` | `02_multistream_batch.py` | 9개 Stream Batch 튜닝 |
| `config/local_pipeline.yaml` | `05_local_synthetic_config.py` | 카메라/GPU 없는 로컬 실행 |

## 1. 설치와 실행 준비

저장소 루트에서 실행한다.

    $env:PYTHONPATH='src'
    python -m pip install -e .

개발 검증까지 하려면 다음을 실행한다.

    python -m pytest -q
    python -m ruff check src\pipeworks tests\sdk examples\01_single_stream_rtsp_style.py examples\02_multistream_batch.py examples\03_multistage_inference.py examples\04_custom_component.py examples\05_local_synthetic_config.py examples\06_observability_server.py

Windows PowerShell이 아닌 환경에서는 PYTHONPATH를 해당 셸 문법에 맞게 설정한다.
설치 후에는 PYTHONPATH 없이도 `pipeworks --version`과 `pipeworks --check`를
사용할 수 있다.

## 2. 권장 학습 순서

### 예제 01: 단일 Stream

파일: `01_single_stream_rtsp_style.py`

가장 기본적인 Pipeline이다.

    RTSPSource
      -> YoloInference
      -> StaticBoxOverlay
      -> DetectionBoxOverlay
      -> SvgSendAction / MQPublishAction
      -> RTSPPublisher

여기서 확인할 내용:

- `.source(...)`는 영상 입력을 선언한다.
- `.inference(...)`는 모델과 stage를 선언한다.
- `.overlay(...)`는 화면에 그릴 명령을 추가한다.
- `.action(...)`은 외부 이벤트를 보낸다.
- `.output(...)`은 결과 영상의 목적지를 선언한다.

실행 결과는 `PipelineResult`로 받는다.

```python
result = pipeline.run()
for context in result.contexts:
    model_result = context.results["YoloInference"]
    for detection in model_result.detections:
        print(detection.label, detection.confidence, detection.box)
```

개발자가 직접 `model.predict(...)`나 `infer(...)`를 호출하지 않는 이유는
Runtime이 Frame/Context 생성, 설정 병합, Stream ID 보존, 결과 저장, 다음
Overlay/Action 단계 전달을 담당하기 때문이다. 모델 경로는 Python 인자로
전달하고 `confidence`, `device`, `fp16`, retry 같은 실행값은 YAML에서 읽는다.

01번의 `YoloInference`는 외부 GPU 없이 예제를 실행하기 위한 결정적 MVP
컴포넌트다. 실제 모델 실행에서는 같은 `.inference(...)` 위치에
`UltralyticsYoloInference` 또는 `TensorRTInference` adapter를 넣고, adapter가
반환한 `DetectionResult`는 동일한 `context.results[stage]` 형식으로 받는다.

실행:

    python examples/01_single_stream_rtsp_style.py

실제 운영에서는 RTSP URL, 모델 경로, Action URL, Output URL만 환경에 맞게
바꾸고 내부 처리 루프는 SDK에 맡긴다.

### 예제 02: Multi-stream Batch

파일: `02_multistream_batch.py`

여러 카메라 Frame을 하나의 Batch로 묶고, 결과를 원래 Stream으로 되돌리는
실행 가능한 예제다. 외부 카메라 없이도 9개 Source와 2개 cycle을 가짜
appsink reader로 실행하므로 Batch 크기와 매핑 결과를 직접 확인할 수 있다.

    Camera 01 ... Camera 09
                 -> Batch Inference
                 -> Stream별 Overlay/Output

개발자가 직접 작성하지 않는 것:

- Batch Collector
- Batch 크기 조절
- 결과 Demultiplex
- stream_id 매핑
- Frame Drop 정책

소스의 핵심 구조:

- `STREAMS`: 카메라 ID, RTSP 입력 주소, MediaMTX 출력 주소를 선언한다.
- `build_sources()`: 각 Stream을 GStreamer RTSP Source로 만든다.
- `Pipeline.run_streams()`: cycle마다 각 Source에서 최대 한 Frame을 모은다.
- `.batch_inference(...)`: 모은 Context를 한 번에 모델에 전달한다.
- SDK Context: 결과의 `stream_id`와 `frame.sequence`를 원본 Frame과 보존한다.
- `MediaMTXPublisher`: 출력 경계에서 Stream별 URL로 전달할 수 있다.

실행:

    python examples/02_multistream_batch.py

실제 연속 입력에서는 예제의 `build_sources()`를 다음처럼 바꾼다.

    sources = build_sources(frame_reader=None)
    result = pipeline.run_streams(sources)

이때 GStreamer 런타임이 각 RTSP URL에서 Frame을 읽으며, Batch 생성/대기,
결과 Demultiplex, Stream ID 보존, 출력 연결은 그대로 SDK가 맡는다. `max_cycles`
는 로컬 테스트용 제한이고 운영에서는 생략한다.

### 예제 03: Multi-stage Inference

파일: `03_multistage_inference.py`

1차 모델 결과를 2차 모델의 입력으로 연결한다.

    Frame
      -> primary inference
      -> DetectionCrop
      -> secondary inference
      -> Overlay
      -> Output

`stage="primary"`, `stage="secondary"`를 지정하면 Context 안에서 두 결과를
서로 덮어쓰지 않고 이름으로 조회할 수 있다.

### 예제 04: Custom Component

파일: `04_custom_component.py`

SDK 코드를 수정하지 않고 회사나 도메인의 규칙을 Processor로 추가한다.

    class CobbleFilter:
        def process(self, context):
            ...

필요한 계약은 `process(context) -> context`다. 같은 방식으로 Source,
Inference, Overlay, Action, Output Protocol을 구현할 수 있다.

### 예제 05: YAML 운영 설정

파일: `05_local_synthetic_config.py`

Python에는 무엇을 연결하는지 남기고, YAML에는 어떻게 실행할지 남긴다.

Python에 둘 것:

- Source 주소 또는 Source Component
- 모델 경로
- 외부 Action 대상
- Output 대상
- stage 이름

YAML에 둘 것:

- confidence
- device / fp16
- timeout / retry
- queue 크기와 drop 정책
- reconnect
- batch 대기 시간
- Action worker 수와 pending 한도

설정 파일: `config/local_pipeline.yaml`

실행:

    python examples/05_local_synthetic_config.py

### 예제 06: Health와 Prometheus

파일: `06_observability_server.py`

로컬에서 한 번만 실행:

    python examples/06_observability_server.py --once

HTTP Endpoint를 열어 실행:

    python examples/06_observability_server.py --host 127.0.0.1 --port 8080

확인:

    curl http://127.0.0.1:8080/health
    curl http://127.0.0.1:8080/metrics

Docker Compose 실행:

    docker compose -f deploy/docker-compose.yml up --build

### 예제 07: Custom Source

파일: `07_custom_source.py`

SDK가 제공하지 않는 카메라나 데이터 수신기를 직접 연결하는 방법이다.

- 단일 실행 Source: `frames() -> list[Frame]`
- 연속 실행 Source: `stream_frames() -> Iterator[Frame]`
- 반드시 `Frame.stream_id`, `Frame.sequence`를 채운다.
- 수신기 내부의 OpenCV loop, SDK 호출, reconnect 구현은 Custom Source 안에 둔다.
- Pipeline 이후의 Batch, Inference, Overlay, Output은 기존 DSL로 조립한다.

실행:

    python examples/07_custom_source.py

실제 수신기를 연결할 때도 `Frame`만 반환하면 된다. SDK Runtime이 결과를
Context에 저장하고 `stream_id`를 끝까지 보존하므로, Custom Source가 추론
호출이나 결과 Demultiplex를 직접 구현하지 않는다.

## 3. 새 Pipeline을 만드는 방법

1. `python -m pipeworks.cli --init-example ./my-pipeline`으로 시작 파일과 `pipeworks.yaml`을 만든다.
2. `pipeline.py`에서 Source, Model, Action, Output을 읽기 좋은 순서로 선언한다.
3. 운영 튜닝값은 `examples/config/`를 참고해 `pipeworks.yaml`에 추가한다.
4. `pipeline.diagram()`으로 사람이 읽는 흐름을 확인한다.
5. `pipeline.validate()`로 구성 오류를 실행 전에 확인한다.
6. 외부 서비스 없이 Synthetic/Mock Source로 테스트한다.
7. 실제 RTSP/GPU/MQ는 optional extra와 Adapter를 통해 연결한다.
8. 테스트, Ruff, `pipeworks --check`를 통과시킨 뒤 배포한다.

## 4. 자주 하는 변경

### 카메라 주소 변경

`RTSPSource("rtsp://camera/main")`의 주소만 변경한다. reconnect, timeout,
drop 정책은 YAML의 `RTSPSource` 항목에서 조정한다.

### 모델 변경

`YoloInference("models/cobble.engine")`의 모델 경로와 stage를 변경한다.
GPU 장치, FP16, confidence는 YAML에서 변경한다.

### 이벤트 전송 추가

`.action(HttpPostAction(...))` 또는 `.action(MQAdapterAction(...))`을
추가한다. Action은 bounded async dispatcher 뒤에서 실행되므로 영상 출력 경로를
직접 막지 않는다.

### 사용자 규칙 추가

`.process(MyProcessor())`를 Pipeline의 원하는 단계에 삽입한다. Processor는
Context를 받아 수정하거나 그대로 반환한다.

### 운영 모니터링 추가

`ObservabilityServer(pipeline)`을 시작하고 `/health`를 readiness 검사,
`/metrics`를 Prometheus scrape 대상으로 연결한다.

## 5. 실행 결과를 읽는 방법

`Pipeline.run()`은 `PipelineResult`를 반환한다.

- `result.contexts`: Stream별 처리 Context
- `result.contexts[i].results`: stage별 Inference 결과
- `result.contexts[i].overlays`: Overlay 명령
- `result.contexts[i].errors`: 격리 모드에서 발생한 Context 오류
- `result.metrics`: 처리량, Queue Drop, Batch, Action 지연과 오류

운영에서 Frame을 버리는 것은 항상 실패가 아니다. 실시간 Pipeline은 오래된
Frame을 계속 쌓는 것보다 최신 Frame을 유지하는 것이 중요할 수 있다. 따라서
drop 정책과 Queue 메트릭을 함께 확인한다.

## 6. 참고 문서

- 프로젝트 전체 방향: [README.md](../README.md)
- 다른 AI Agent 인수인계: [AGENTS.md](../AGENTS.md)
- YAML 설정 전체 reference: [configuration.md](../docs/configuration.md)
- 예제 YAML 설명: [config/README.md](config/README.md)
- 배포 템플릿: [deploy/README.md](../deploy/README.md)
- Pipeline 설계: [pipeline-sdk-design.md](../docs/pipeline-sdk-design.md)
- 런타임 구조: [architecture.md](../docs/architecture.md)

`examples/single_stream.py`, `multi_stream_batch.py`, `multi_stage_inference.py`,
`custom_component.py`, `metadata.py`, `nvidia_*` 파일은 이전 프로젝트의
참고/백업 예제다. 새 SDK를 학습할 때는 번호가 붙은 공식 예제를 우선한다.
