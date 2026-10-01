# Pipe Works 개발자 실전 가이드

이 문서는 영상 처리 SDK를 처음 사용하는 개발자가 그대로 따라 할 수 있는
작업 순서다. 목표는 카메라 수신 코드부터 추론, 결과 매핑, 출력, 테스트를
각자 다시 만드는 것이 아니라 **Pipeline을 선언하고 필요한 확장 지점만 구현하는 것**이다.

## 0. 먼저 이해할 것

Python 파일에는 Pipeline의 의미(What)를 쓴다.

- Source 주소와 Stream ID
- 모델 경로와 stage 이름
- Transform/Overlay/Action/Output의 순서
- 외부 Action 대상과 출력 대상

YAML 파일에는 동작 방식(How)을 쓴다.

- confidence, device, FP16
- timeout, retry, reconnect
- queue/drop/batch 정책
- freshness budget과 latency 제한
- codec, FPS, bitrate

`pipeline.py`를 10초 안에 읽고 영상 흐름을 이해할 수 있어야 한다.

## 1. 설치와 첫 실행

저장소 루트에서 실행한다.

PowerShell:

```powershell
$env:PYTHONPATH='src'
python -m pip install -e .
python -m pipeworks.cli --check
```

macOS/Linux:

```bash
export PYTHONPATH=src
python -m pip install -e .
python -m pipeworks.cli --check
```

`--check`는 Ruff와 SDK 테스트를 실행한다. 카메라, GPU, MQ가 없어도 통과해야
정상이다.

## 2. 새 프로젝트 만들기

```powershell
python -m pipeworks.cli --init-example .\my-pipeline
cd .\my-pipeline
python pipeline.py
```

생성되는 파일:

```text
my-pipeline/
  pipeline.py       # Pipeline 선언과 결과 조회
  pipeworks.yaml    # 운영 튜닝값
```

처음에는 `SyntheticSource`로 흐름을 확인한다. 실제 RTSP로 바꾸기 전까지
외부 장비를 요구하지 않는 상태를 유지한다.

## 3. 첫 Pipeline 작성

```python
from pipeworks import (
    DetectionBoxOverlay,
    Pipeline,
    RTSPPublisher,
    RTSPSource,
    YoloInference,
)

pipeline = (
    Pipeline("my-camera", config="pipeworks.yaml")
    .source(RTSPSource("rtsp://camera/main"))
    .inference(YoloInference("models/cobble.engine"))
    .overlay(DetectionBoxOverlay())
    .output(RTSPPublisher("rtsp://mediamtx/cobble"))
)
```

호출 순서가 곧 처리 순서다. 개발자가 `model.predict()`나 Frame loop를 직접
작성하지 않는다.

## 4. 결과 받기

`run()`은 `PipelineResult`를 반환한다.

```python
result = pipeline.run()

for context in result.contexts:
    # stage 이름은 Inference component의 name/stage다.
    detections = context.results["YoloInference"].detections

    for detection in detections:
        print(
            context.stream_id,
            context.frame.sequence,
            detection.label,
            detection.confidence,
            detection.box,
        )

print(result.metrics.to_json())
```

결과 구조:

```text
PipelineResult
  ├─ contexts[]
  │   ├─ frame
  │   ├─ results[stage]
  │   ├─ overlays
  │   └─ errors
  └─ metrics
```

여러 모델을 연결하면 `context.results["primary"]`,
`context.results["secondary"]`처럼 stage별 결과를 조회한다.

## 5. YAML 작성

```yaml
Pipeline:
  worker_queue_size: 64
  worker_drop_policy: latest

YoloInference:
  confidence: 0.7
  device: cpu
  fp16: false
  inference_retry: 1

Realtime:
  max_end_to_end_latency_ms: 1000
  max_frame_age_ms: 800
  drop_expired_frames: true
  output_latency_action: drop
```

주소와 모델 경로를 YAML로 옮기지 않는다. 모든 설정 키는
[configuration.md](../docs/configuration.md)에서 확인한다.

## 6. 9채널 Batch Pipeline

```python
pipeline = (
    Pipeline("nine-cameras", config="pipeworks.yaml")
    .streams([
        Stream("cam01", "rtsp://cam01", "rtsp://mediamtx/cam01"),
        Stream("cam02", "rtsp://cam02", "rtsp://mediamtx/cam02"),
    ])
    .batch_inference(YoloInference("models/cobble.engine"))
    .overlay(DetectionBoxOverlay())
)

result = pipeline.run_streams({
    "cam01": GStreamerRTSPSource("rtsp://cam01", "cam01"),
    "cam02": GStreamerRTSPSource("rtsp://cam02", "cam02"),
})
```

Batch 생성과 결과 Demultiplex는 SDK가 처리한다. 개발자가 Batch list를 만들거나
결과를 다시 Camera별로 나누지 않는다. 전체 실행 예제는
`02_multistream_batch.py`를 참고한다.

## 7. Custom Source

단일 실행 Source는 다음 계약을 구현한다.

```python
class MySource:
    def frames(self):
        yield Frame("my-camera", image=read_frame(), sequence=0)
```

연속 Source는 다음 계약을 구현한다.

```python
class MyLiveSource:
    def stream_frames(self):
        sequence = 0
        while True:
            yield Frame("my-camera", image=receive_frame(), sequence=sequence)
            sequence += 1
```

반드시 `stream_id`, `sequence`, 가능하면 입력 시각이 포함된 `Frame`을 반환한다.
전체 유한/연속 Source 예제는 `07_custom_source.py`에 있다.

## 8. Custom 처리 로직

추론 결과를 도메인 규칙으로 필터링할 때는 Processor를 추가한다.

```python
class CobbleFilter:
    def process(self, context):
        context.detections = [
            detection
            for detection in context.detections
            if detection.confidence >= 0.7
        ]
        return context


pipeline = pipeline.process(CobbleFilter())
```

모델 자체를 교체해야 하면 `InferenceComponent` 계약의 `infer()` 또는
`infer_batch()`를 구현한다. 표준 모델은 `YoloInference`/adapter를 사용하고,
특수 모델만 Custom Inference를 만든다.

## 9. 테스트 작성

카메라 없이 Custom Source와 Synthetic Source를 사용해 결정적 테스트를 만든다.

```python
from pipeworks import Pipeline, SyntheticSource, YoloInference


def test_pipeline_keeps_detection_result():
    result = (
        Pipeline("test")
        .source(SyntheticSource("cam01", frame_count=2))
        .inference(YoloInference("models/test.engine"))
        .run()
    )

    assert len(result.contexts) == 2
    assert result.contexts[0].results["YoloInference"].detections
```

실행:

```powershell
$env:PYTHONPATH='src'
python -m pytest -q
python -m ruff check src\pipeworks tests\sdk examples\01_single_stream_rtsp_style.py examples\02_multistream_batch.py examples\03_multistage_inference.py examples\04_custom_component.py examples\05_local_synthetic_config.py examples\06_observability_server.py examples\07_custom_source.py
python -m pipeworks.cli --check
```

## 10. 실제 운영으로 전환

1. `SyntheticSource`를 실제 Source로 교체한다.
2. `YoloInference`를 `UltralyticsYoloInference` 또는 `TensorRTInference`로 교체한다.
3. CUDA/GStreamer 시스템 런타임과 Python extra를 설치한다.
4. 모델 경로와 Secret은 배포 환경에서 주입한다.
5. MediaMTX 실제 publish adapter를 연결한다.
6. `/health`, `/metrics`를 readiness와 Prometheus에 연결한다.
7. 9채널 부하에서 end-to-end p95 latency가 1,000ms 이하인지 확인한다.

실제 모델 adapter는 배포 환경의 CUDA binding이 필요하다. 따라서 로컬 예제가
통과했다고 실제 GPU/RTSP/MediaMTX 운영이 검증된 것은 아니다.

## 11. 자주 발생하는 문제

| 증상 | 확인할 것 |
| --- | --- |
| `ModuleNotFoundError: pipeworks` | `PYTHONPATH=src` 또는 `pip install -e .` |
| GStreamer runtime 오류 | `gstreamer` extra와 시스템 GStreamer 설치 |
| TensorRT session 오류 | CUDA/TensorRT 설치와 `TensorRTSessionFactory` 주입 |
| 결과가 비어 있음 | `context.results`의 정확한 stage 이름 확인 |
| Stream ID mismatch | Source가 요청된 stream_id로 Frame을 반환하는지 확인 |
| latency가 계속 증가 | `latest`, bounded queue, `Realtime` drop 설정과 metrics 확인 |
| Action 때문에 영상이 느려짐 | Action queue/drop metrics와 async dispatcher 확인 |

## 완료 체크리스트

- [ ] Python DSL만 읽어도 입력/모델/출력 흐름이 보인다.
- [ ] 튜닝값은 YAML에 있고 주소/모델/대상은 Python에 있다.
- [ ] `PipelineResult`에서 stage 결과를 읽는다.
- [ ] Custom Source는 `Frame` 계약을 지킨다.
- [ ] 외부 장비 없이 테스트가 재현된다.
- [ ] `pytest`, Ruff, `pipeworks --check`가 통과한다.
- [ ] 실제 환경에서 latency p95와 expired drop을 확인했다.
