# Pipe Works: 실시간 영상 처리 SDK

영상 스트림을 처리하는 실시간 파이프라인을 **선언형 API**로 만드는 Python SDK입니다.

배포본에서 별도 앱을 만드는 절차와 전체 모듈 계약은 [사용 설명서](docs/pipeworks/README.md)를 참고하세요. [설치와 앱 실행](docs/pipeworks/getting_started.md)부터 시작하며 specs는 사용에 필요하지 않습니다.  
사람도 이해하고, **AI Agent도 이를 기반으로 실제 애플리케이션을 구현**할 수 있습니다.

---

## 🎯 핵심 특징

- **선언형 파이프라인**: Step을 순차 연결하기만 하면 됨
- **동적 코드 재로드**: 실행 중 Step 코드 변경 가능 (Hotswap)
- **실시간 처리**: RTSP 스트림, YOLO, NVIDIA GPU 최적화
- **AI 친화적 문서**: README만으로도 AI Agent가 애플리케이션 구현 가능

전처리와 후처리를 개별 단계로 구성하려면 [YoloInference](docs/pipeworks/embedded/yolo_inference.md)를 사용합니다. GPU `model_input`을 받아 이름별 `model_output`에 모든 원시 출력을 전달합니다. 기본 TorchScript와 사용자 GPU 실행부는 특정 YOLO 라이브러리에 의존하지 않으며, 전처리·후처리 구현은 examples/step의 두 YOLO 예제 파일에서 제공하며 코어에는 포함하지 않습니다.

---

## ⚡ 1분 만에 이해하기

### 파이프라인의 흐름

```
RTSPSource → NvidiaDecode → YoloPreProcess → YoloInference → YoloPostProcess → NvidiaEncode → RTSPPublish
```

### 최소 코드

examples가 모듈 탐색 경로에 있도록 실행하거나 예제 단계 파일을 애플리케이션에 포함합니다.

```python
from pathlib import Path
from pipeworks import Backend, Pipeline
from pipeworks.embedded import RTSPSource, NvidiaDecode, YoloInference, NvidiaEncode, RTSPPublish
from step.yolo_pre_process import YoloPreProcess
from step.yolo_post_process import YoloPostProcess

pipeline = Pipeline("my-pipeline", config=Path("config.yaml"))
pipeline.step(RTSPSource(url="rtsp://camera/main"))
pipeline.step(NvidiaDecode())
pipeline.step(YoloPreProcess())
pipeline.step(YoloInference(Path("models/yolo11n.pt"), backend=Backend.ULTRALYTICS))
pipeline.step(YoloPostProcess())
pipeline.step(NvidiaEncode())
pipeline.step(RTSPPublish(url="rtsp://mediamtx:8554/output"))
pipeline.run()
```

Batch 추론이 없는 파이프라인은 호출자 프로세스에서 실행합니다. 래퍼 내부를 포함해 `YoloInference(batch=True)`가 하나라도 있으면 전체 파이프라인을 중앙 프로세스에서 실행합니다. 두 경로는 같은 단계 실행기를 사용합니다.

Batch 실행에서 운영과 개발의 중앙 프로세스를 분리하려면 `Pipeline("development", config=Path("stream.yml"), development=True)`로 생성하고 `pipeline.run()`으로 실행합니다. `development` 기본값은 `False`로 운영용입니다. 같은 모드끼리 프로세스와 모델 작업자를 공유합니다. 다른 모드에서는 모델을 따로 로드하고 같은 GPU의 자원은 공유합니다. [중앙 프로세스 그룹 안내](docs/pipeworks/main.md)를 참고하세요.

### config.yaml (YAML 설정)

```yaml
RTSPSource:
  reconnect: true
  reconnect_interval_ms: 3000
  transport: tcp
  timeout_ms: 5000

YoloInference:
  backend: ultralytics
  gpu_id: 0

YoloPostProcess:
  classes: null  # null = 모든 클래스
  confidence: 0.25

RTSPPublish:
  reconnect: true
  transport: tcp
```

---

## 📚 핵심 개념

예제 `examples/step/tensor_rt_pre_process.py`의 `TensorRTPreProcess`는 GPU NV12·RGB·BGR 이미지를 모델별 입력으로 변환합니다. 모델의 전처리 규칙에 맞춰 예제 코드와 생성자에서 크기 변경 방식, 채널 순서, 정규화, FP16/FP32와 NCHW/NHWC를 지정합니다. 제공 YAML에는 전처리 설정이 없으며 기본 예제는 생성자 기본값을 사용합니다. 아래 가져오기는 `examples`가 모듈 탐색 경로에 있을 때 사용할 수 있습니다. 전체 옵션과 탐지·분류 설정은 [사용자 Step 작성 안내](docs/pipeworks/custom_steps.md)를 참고하세요.

```python
from step.tensor_rt_pre_process import TensorRTPreProcess

preprocess = TensorRTPreProcess(size=(640, 640), dtype="float16")
```

### Step
파이프라인의 기본 단위입니다. 입력 스트림을 받아 처리 후 출력합니다.

`configure()`와 `process()`는 모두 필수 구현 메서드입니다. 설정이 필요 없으면 빈 `configure()`를 구현합니다. 구체 구현을 상속할 수도 있으며, 구현이 누락된 Step은 생성 시 `TypeError`가 발생합니다.

```python
class Step(ABC):
    @abstractmethod
    def configure(self, config: SimpleNamespace) -> None:
        """YAML 설정을 적용합니다."""
        pass
    
    @abstractmethod
    def process(self, inputs: Iterator[PipelineContext]) -> Iterator[PipelineContext]:
        """입력을 받아 처리 후 출력합니다."""
        pass
```

**Step의 종류:**
- **Source Step** (RTSPSource): 영상을 읽어들임
- **Processing Step** (YoloInference, CustomProcessor): 데이터 처리
- **Sink Step** (RTSPPublish): 결과를 출력/저장
- **TapSkipIfBusy Step** (TapSkipIfBusy): 원본을 전달하면서 배경 후처리 실행

### PipelineContext
스트림의 각 "프레임" 또는 "패킷" 단위 데이터입니다. `video_stream`은 연결당 한 번 생성해 공유하는 불변 `VideoStreamInfo`이며 원본 컨테이너 종료 후에도 값이 유지됩니다. 기존 `codec_context.width`·`height` 접근은 유지됩니다.

```python
# 사용자 정의 Source Step에서 연결당 한 번 생성
from pipeworks.video import VideoStreamInfo

stream_info = VideoStreamInfo.from_stream(stream)  # 컨테이너가 열린 동안 호출
context = PipelineContext(
    video_stream=stream_info,
    packet=packet,
    # 다른 필드들...
)

# Processing Step에서 추가
context.detections = results
context.custom_field = value

# 하류 Step에서 사용
for context in inputs:
    print(context.detections)
```

### Pipeline
전체 파이프라인을 조립하고 실행합니다.

```python
pipeline = Pipeline(name="my-pipeline", config=Path("config.yaml"))
pipeline.step(step1).step(step2).step(step3)
result = pipeline.run()
```

### Hotswap
실행 중 Step의 코드를 재로드합니다. Custom Step을 개발할 때 유용합니다.

```python
# config.yaml를 변경하면 자동으로 재적용됨
# Step의 .py 파일을 수정하면 자동으로 재로드됨
```

---

## 🧩 내장 Step 레퍼런스

전체 Step의 구현 파일과 최신 명세는 [Step 명세 목록](docs/pipeworks/README.md)에서 확인합니다.

### Source Step (스트림 입력)

#### **RTSPSource**
RTSP 카메라에서 영상을 읽습니다.

- **역할**: RTSP 압축 패킷 수신. 디코딩은 NvidiaDecode에서 수행
- **사용**: `pipeline.step(RTSPSource(url="rtsp://camera/main"))`
- **설정**: `reconnect`, `reconnect_interval_ms`, `transport`, `timeout_ms`
- **상세**: [docs/pipeworks/embedded/rtsp_source.md](docs/pipeworks/embedded/rtsp_source.md)

---

### Processing Step (데이터 처리)

#### **EveryNFrames**

- **역할**: 첫 입력부터 N프레임마다 내부 Step 묶음을 실행하고 나머지 입력은 그대로 전달합니다.
- **사용**: `pipeline.step(EveryNFrames(preprocess, inference, postprocess, interval_frames=3))`
- **설정**: `EveryNFrames` YAML 섹션의 `interval_frames`(기본 1). 내부 Step은 각 클래스명 섹션을 사용합니다.
- **상세**: [EveryNFrames 안내](docs/pipeworks/embedded/every_n_frames.md)

#### **CudaAsync**
다른 처리 단계를 비동기로 실행하고 원본 사용 종료가 확인된 타임아웃·정리된 오류·작업자 사용 중에는 원본을 전달합니다. 타임아웃에 아직 사용 중인 프레임은 폐기합니다.

- **사용**: `pipeline.step(CudaAsync(processor, timeout_ms=5))`
- **설정**: `timeout_ms`. 내부 단계는 각 클래스명 최상위 YAML 섹션을 사용합니다.
- **지원**: 입력 하나당 출력 하나인 단계. 공유 입력은 읽기 전용이며 보호 복사는 하지 않습니다. YOLO와 예제 TensorRT 전처리는 RGB 생성 후 원본 사용 종료를 알립니다. 늦은 결과는 폐기합니다.
- **상세**: [CudaAsync 안내](docs/pipeworks/embedded/cuda_async.md)

#### **YoloInference**

- **역할**: 준비된 GPU `model_input`을 실행하여 모든 원시 GPU 출력을 이름별 `model_output`으로 전달합니다. TorchScript 실행부는 TorchScript이며 사용자 실행부를 선택할 수 있습니다.
- **사용**: `pipeline.step(YoloInference(Path("models/yolo11n.pt"), backend=Backend.ULTRALYTICS))`
- **연결**: 전처리 → `YoloInference` → 후처리 순서로 구성하며 개별·공유 배치와 `CudaAsync`를 지원합니다.
- **상세**: [YoloInference 안내](docs/pipeworks/embedded/yolo_inference.md)

예제의 `step.yolo_pre_process.YoloPreProcess`와 `step.yolo_post_process.YoloPostProcess`를 앞뒤로 연결하면 GPU 전처리·NMS·좌표 복원을 수행하고 `YoloReport`에서 전체 YOLO 처리 시간을 확인할 수 있습니다. 전처리는 기본 RGB NCHW FP32, 후처리는 모든 COCO 클래스를 대상으로 하며 생성자와 클래스별 YAML로 설정합니다.

#### **YoloInference의 TensorRT 실행**

YOLO와 TensorRT 전후처리 예제는 같은 옵션과 `image_transform` 계약을 사용하므로 전후처리를 유지하고 추론 단계만 교체할 수 있습니다. 두 후처리의 기본 클래스 필터는 `None`이며 차량만 필요하면 `classes=[2]`를 지정합니다. [공통 계약과 교체 예제](docs/pipeworks/embedded/yolo_inference.md)를 참고하세요.
전처리 단계의 `context.model_input` GPU 텐서를 TensorRT로 추론하고 `context.model_output`에 원시 GPU 출력을 저장합니다.

- **입출력**: 단일 텐서 또는 입력 이름별 GPU 텐서 사전 → 출력 이름별 GPU 텐서 사전. 바인딩 이름은 엔진에서 읽습니다.
- **사용**: `pipeline.step(YoloInference(Path("models/model.engine"), backend=Backend.TENSORRT))`
- **설정**: 클래스명 YAML의 `gpu_id`, `profile_index`(기본 0); 모델 동명 `.yml`의 `plugins`(기본 빈 목록), 배치 수집용 `max_batch_size`·`timeout_ms`
- **동작**: 전처리·후처리 없이 동기 추론하며 GPU 완료 후 결과를 전달합니다. 연속 입력은 복제하지 않고 오류는 전파합니다. 시간 제한·오류 통과는 공통 Async로 적용합니다.
- **상세**: [TensorRT 엔진 안내](docs/pipeworks/embedded/tensor_rt_inference.md)

#### **NvidiaDecode**
NVIDIA GPU를 이용해 RTSP 패킷을 디코딩합니다.

- **역할**: 하드웨어 가속 비디오 디코딩
- **사용**: `pipeline.step(NvidiaDecode())`
- **설정**: `gpu_id` (기본값 `0`)
- **전달 정책**: 내부 스레드에서 수신·디코딩을 계속 수행하며, 대기 프레임을 최대 30개 보관하며 초과 시 가장 오래된 대기 프레임을 버립니다. 후속 단계가 느리면 소비 전 프레임을 버립니다.
- **메모리**: 잠금 디코더 버퍼를 복사 없이 공유하고 GPU 작업 완료 후 반환합니다. 잠금 출력 보관량은 최대 34개입니다.
- **상세**: [docs/pipeworks/embedded/nvidia_decode.md](docs/pipeworks/embedded/nvidia_decode.md)

#### **StreamReport**
파이프라인 성능 지표를 수집합니다 (수신율, 추론 시간 등).

- **역할**: 성능 모니터링 및 로깅
- **사용**: `pipeline.step(StreamReport())`
- **설정**: 없음 (자동 수집)
- **상세**: [docs/pipeworks/embedded/stream_report.md](docs/pipeworks/embedded/stream_report.md)

#### **YoloReport**
감지 경로의 전처리, 배치 큐 대기, 입력 결합, 모델 실행, 후처리, 출력 복사와 전체 지연을 비교합니다.

- **사용**: 감지 단계 뒤에 `pipeline.step(YoloReport())`. CudaAsync 사용 시 래퍼 바깥에 둡니다.
- **출력**: 구간별 CPU/GPU 시간, 1초·최근 10초 평균과 표본 수, 완료·건너뜀·바쁨·타임아웃·오류 건수.
- **측정**: 모델 실행은 NMS를 제외합니다. 측정 때문에 추가 GPU 동기화를 넣지 않습니다.
- **상세**: [감지 성능 리포트 안내](docs/pipeworks/embedded/yolo_report.md)

---

### Sink Step (결과 출력)

#### **RTSPPublish**
처리된 영상을 RTSP로 발행합니다.

- **역할**: 압축 패킷 RTSP 송출. 인코딩은 NvidiaEncode에서 수행
- **사용**: `pipeline.step(RTSPPublish(url="rtsp://mediamtx:8554/camera"))`
- **설정**: `reconnect`, `reconnect_interval_ms`, `transport`, `timeout_ms`, `packet_size`
- **상세**: [docs/pipeworks/embedded/rtsp_publish.md](docs/pipeworks/embedded/rtsp_publish.md)

#### **NvidiaEncode**
NVIDIA GPU를 이용해 영상을 인코딩합니다.

- **역할**: 하드웨어 가속 비디오 인코딩
- **사용**: `pipeline.step(NvidiaEncode())`
- **설정**: `gpu_id`, `fps`
- **상세**: [docs/pipeworks/embedded/nvidia_encode.md](docs/pipeworks/embedded/nvidia_encode.md)

#### **TapSkipIfBusy**
원본을 다음 단계로 전달하면서 별도 작업자에서 후처리를 실행합니다. 수락한 배경 입력은 별도 컨텍스트로 만들어 최상위 속성과 핫스왑 변경 정보를 분리합니다. 영상·GPU 버퍼와 중첩 데이터는 참조를 공유하므로 배경 처리는 공유 데이터를 읽기 전용으로 사용합니다.

- **역할**: 배경 후처리, 작업 중 새 입력은 후처리에서 건너뛰기
- **사용**: `pipeline.step(TapSkipIfBusy(step=MyFinalStep()))`
- **설정**: Step별로 상이
- **상세**: [docs/pipeworks/embedded/tap_skip_if_busy.md](docs/pipeworks/embedded/tap_skip_if_busy.md)

---

## 🔧 Custom Step 만드는 법

자신만의 Step을 만들어 파이프라인에 추가합니다.

### 최소 구현

```python
from types import SimpleNamespace
from typing import Iterator
from pipeworks.models import PipelineContext, Step


class MyCustomStep(Step):
    def __init__(self):
        self.threshold = 0.5

    def configure(self, config: SimpleNamespace) -> None:
        """YAML 설정을 읽어서 자신의 속성을 설정합니다."""
        self.threshold = getattr(config, "threshold", 0.5)

    def process(self, inputs: Iterator[PipelineContext]) -> Iterator[PipelineContext]:
        """입력을 받아 처리 후 출력합니다."""
        for context in inputs:
            # context는 이전 Step에서 생성한 PipelineContext
            # context.detections, context.packet, context.video_stream 등 접근 가능

            # 처리 로직
            result = self.my_processing(context)

            # 결과를 context에 저장
            context.my_result = result

            yield context

    def my_processing(self, context):
        # 실제 처리 코드
        return "processed"
```

### config.yaml에서 설정

```yaml
MyCustomStep:
  threshold: 0.7
```

### 파이프라인에서 사용

```python
from pathlib import Path
from pipeworks import Pipeline
from my_module import MyCustomStep

pipeline = Pipeline("custom-pipeline", config=Path("config.yaml"))
pipeline.step(RTSPSource(url="rtsp://camera"))
pipeline.step(MyCustomStep())
pipeline.step(RTSPPublish(url="rtsp://mediamtx:8554/{stream_id}"))
pipeline.run()
```

### Hotswap으로 개발 중 재로드

파이프라인 실행 중 `MyCustomStep`의 `.py` 파일을 수정하면:
- 다음 epoch에 자동으로 재로드됨
- 이전 context는 원래 코드로 처리, 새 context는 새 코드로 처리
- config.yaml을 수정하면 자동으로 `configure()`를 다시 호출

---

## 📖 전체 모듈 문서

| 모듈 | 설명 | 문서 |
|------|------|------|
| **Pipeline** | 전체 파이프라인 조립 및 실행 | [docs/pipeworks/pipeline.md](docs/pipeworks/pipeline.md) |
| **Hotswap** | 실행 중 코드/설정 재로드 | [docs/pipeworks/hotswap.md](docs/pipeworks/hotswap.md) |
| **Models** | PipelineContext, Step 기본 클래스 | [docs/pipeworks/models.md](docs/pipeworks/models.md) |
| **Main** | 중앙 스트림 프로세싱 (내부용) | [docs/pipeworks/main.md](docs/pipeworks/main.md) |
| **공유 YOLO 추론** | 세 backend와 감지의 공유 GPU 배치 실행 | [docs/pipeworks/local_yolo_inference.md](docs/pipeworks/local_yolo_inference.md) |

### Embedded Step 문서

| Step | 문서 |
|------|------|
| EveryNFrames | [EveryNFrames 안내](docs/pipeworks/embedded/every_n_frames.md) |
| CudaAsync | [CudaAsync 안내](docs/pipeworks/embedded/cuda_async.md) |
| RTSPSource | [docs/pipeworks/embedded/rtsp_source.md](docs/pipeworks/embedded/rtsp_source.md) |
| YoloInference | [docs/pipeworks/embedded/yolo_inference.md](docs/pipeworks/embedded/yolo_inference.md) |
| RTSPPublish | [docs/pipeworks/embedded/rtsp_publish.md](docs/pipeworks/embedded/rtsp_publish.md) |
| NvidiaDecode | [docs/pipeworks/embedded/nvidia_decode.md](docs/pipeworks/embedded/nvidia_decode.md) |
| NvidiaEncode | [docs/pipeworks/embedded/nvidia_encode.md](docs/pipeworks/embedded/nvidia_encode.md) |
| TapSkipIfBusy | [docs/pipeworks/embedded/tap_skip_if_busy.md](docs/pipeworks/embedded/tap_skip_if_busy.md) |
| StreamReport | [docs/pipeworks/embedded/stream_report.md](docs/pipeworks/embedded/stream_report.md) |

---

## 🚀 실제 예제들

### 예제 1: RTSP → YOLO 객체 감지 → RTSP 발행

```python
from pipeworks import Backend
from step.yolo_pre_process import YoloPreProcess
from step.yolo_post_process import YoloPostProcess

from pathlib import Path
from pipeworks import Pipeline
from pipeworks.embedded import RTSPSource, YoloInference, RTSPPublish

pipeline = Pipeline("rtsp-yolo-pipeline", config=Path("config.yaml"))
pipeline.step(RTSPSource(url="rtsp://camera/main"))
pipeline.step(YoloPreProcess()).step(YoloInference(model_path=Path("models/yolo11n.pt"), backend=Backend.ULTRALYTICS)).step(YoloPostProcess())
pipeline.step(RTSPPublish(url="rtsp://mediamtx:8554/{stream_id}"))
pipeline.run()
```

**config.yaml:**
```yaml
RTSPSource:
  reconnect: true
  reconnect_interval_ms: 3000

YoloInference:
  backend: ultralytics
  gpu_id: 0

YoloPostProcess:
  confidence: 0.5

RTSPPublish:
  transport: tcp
  timeout_ms: 5000
```

---

### 예제 2: 여러 RTSP 카메라 동시 처리

```python
from pipeworks import Backend
from step.yolo_pre_process import YoloPreProcess
from step.yolo_post_process import YoloPostProcess

from pathlib import Path
from pipeworks import Pipeline
from pipeworks.embedded import RTSPSource, YoloInference, StreamReport, RTSPPublish

# 각 카메라별로 독립적인 파이프라인 생성
cameras = [
    ("cam01", "rtsp://camera1/main"),
    ("cam02", "rtsp://camera2/main"),
]

for cam_id, cam_url in cameras:
    pipeline = Pipeline(f"pipeline-{cam_id}", config=Path("config.yaml"))
    pipeline.step(RTSPSource(url=cam_url))
    pipeline.step(YoloPreProcess()).step(YoloInference(model_path=Path("models/yolo11n.pt"), backend=Backend.ULTRALYTICS)).step(YoloPostProcess())
    pipeline.step(StreamReport())
    pipeline.step(RTSPPublish(url=f"rtsp://mediamtx:8554/{cam_id}"))
    # 각 파이프라인을 백그라운드에서 실행
    import threading

    thread = threading.Thread(target=pipeline.run, daemon=True)
    thread.start()

# 메인 스레드 계속 실행
import time

while True:
    time.sleep(1)
```

---

### 예제 3: Custom Step과 Hotswap으로 실시간 개발

**my_filter.py:**
```python
from types import SimpleNamespace
from typing import Iterator
from pipeworks.models import PipelineContext, Step


class MyFilter(Step):
    def __init__(self):
        self.min_confidence = 0.5

    def configure(self, config: SimpleNamespace) -> None:
        self.min_confidence = getattr(config, "min_confidence", 0.5)

    def process(self, inputs: Iterator[PipelineContext]) -> Iterator[PipelineContext]:
        for context in inputs:
            results = getattr(context, "detections", None) or {}
            result = results.get("yolo11n.pt")
            if result is not None:
                # confidence 필터링
                filtered = [
                    det for det in result.boxes.conf if det >= self.min_confidence
                ]
                if filtered:
                    yield context
            else:
                yield context
```

**config.yaml:**
```yaml
MyFilter:
  min_confidence: 0.6
```

**pipeline.py:**
```python
from pipeworks import Backend
from step.yolo_pre_process import YoloPreProcess
from step.yolo_post_process import YoloPostProcess

from pathlib import Path
from pipeworks import Pipeline
from pipeworks.embedded import RTSPSource, YoloInference, RTSPPublish
from my_filter import MyFilter

pipeline = Pipeline("live-dev-pipeline", config=Path("config.yaml"))
pipeline.step(RTSPSource(url="rtsp://camera/main"))
pipeline.step(YoloPreProcess()).step(YoloInference(model_path=Path("models/yolo11n.pt"), backend=Backend.ULTRALYTICS)).step(YoloPostProcess())
pipeline.step(MyFilter())  # 여기서 Hotswap이 적용됨
pipeline.step(RTSPPublish(url="rtsp://mediamtx:8554/output"))
pipeline.run()
```

**개발 중:**
- `my_filter.py`를 수정 → 자동으로 재로드됨
- `config.yaml`의 `min_confidence` 값 변경 → 자동으로 `configure()`가 다시 호출됨
- 파이프라인은 계속 실행되면서 업데이트됨

---

## 🔌 의존성 설치

현재 프로젝트 배포 이름은 pipe-works, import 이름은 pipeworks입니다. Python 3.11.9와 pyproject.toml의 고정 GPU 의존성을 사용합니다. 선택적 av·yolo·nvidia·all extras는 정의되어 있지 않습니다.

```powershell
Set-Location D:\SDK\pipe-works
uv sync --locked
```

CUDA 패키지 공급 경로와 별도 앱에서 SDK 환경의 Python을 사용하는 방법은 [설치·실행 안내](docs/pipeworks/getting_started.md)에 설명되어 있습니다. 문서는 wheel에 자동 포함되지 않으므로 배포 시 docs도 함께 제공합니다.

---

## 🐛 자주 묻는 질문

### Q1: 파이프라인을 중단하려면?

파이프라인 실행 중 `Ctrl+C`를 누르면 graceful shutdown됩니다.

```python
try:
    pipeline.run()
except KeyboardInterrupt:
    print("파이프라인 중단됨")
```

### Q2: RTSP 재연결이 안 되는데?

`config.yaml`에서 설정을 확인하세요:

```yaml
RTSPSource:
  reconnect: true
  reconnect_interval_ms: 5000  # 밀리초 단위
  timeout_ms: 10000
```

### Q3: YOLO 모델은 어디서 받나?

[Ultralytics YOLOv8 모델](https://docs.ultralytics.com/models/yolov8/)에서 다운로드할 수 있습니다:

```bash
# 모델 다운로드
from ultralytics import YOLO
model = YOLO("yolov8n.pt")  # nano 모델 (가벼움)
model = YOLO("yolov8m.pt")  # medium 모델 (균형)
model = YOLO("yolov8l.pt")  # large 모델 (정확)
```

### Q4: Custom Step에서 다른 라이브러리를 쓸 수 있나?

네, 자유롭게 사용할 수 있습니다:

```python
import cv2
import numpy as np
from types import SimpleNamespace
from typing import Iterator
from pipeworks.models import PipelineContext, Step


class MyOpenCVStep(Step):
    def configure(self, config: SimpleNamespace) -> None:
        pass

    def process(self, inputs: Iterator[PipelineContext]) -> Iterator[PipelineContext]:
        for context in inputs:
            # OpenCV 사용
            frame = get_frame_from_context(context)  # 자신의 유틸 함수
            result = cv2.Canny(frame, 100, 200)
            context.edges = result
            yield context
```

---

## 📞 지원

문제가 발생하면:
1. 각 모듈의 상세 문서 (`docs/pipeworks/*.md`)를 확인하세요
2. 로그에서 에러 메시지를 확인하세요
3. 설정(`config.yaml`)이 올바른지 확인하세요
4. GitHub Issues에 버그를 보고하세요

---

## 📄 라이선스

MIT License

---

**다음 단계:** 특정 모듈에 대해 알아보려면 위의 "전체 모듈 문서" 섹션에서 링크를 클릭하세요.

추론 단계는 `YoloInference`로 통합되었습니다. `Backend.ULTRALYTICS`, `Backend.TORCHSCRIPT`, `Backend.TENSORRT`로 실행 방식을 선택합니다. TensorRT의 `profile_index`와 공유 배치·플러그인·GPU 입출력 계약은 유지되며 `YoloReport`를 연결합니다.

`YoloReport`는 모든 추론 backend를 활성화하고 `YOLO`, `ULTRALYTICS`, `TORCHSCRIPT`, `TensorRT`별로 처리 시간과 상태를 구분하여 출력합니다. 공유 배치·전후처리·비동기 상태는 같은 보고 저장소로 연결됩니다.
