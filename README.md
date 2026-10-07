# Pipe Works: AI-Powered Video Stream Processing SDK

영상 스트림을 처리하는 실시간 파이프라인을 **선언형 API**로 만드는 Python SDK입니다.  
사람도 이해하고, **AI Agent도 이를 기반으로 실제 애플리케이션을 구현**할 수 있습니다.

---

## 🎯 핵심 특징

- **선언형 파이프라인**: Step을 순차 연결하기만 하면 됨
- **동적 코드 재로드**: 실행 중 Step 코드 변경 가능 (Hotswap)
- **실시간 처리**: RTSP 스트림, YOLO, NVIDIA GPU 최적화
- **AI 친화적 문서**: README만으로도 AI Agent가 애플리케이션 구현 가능

---

## ⚡ 1분 만에 이해하기

### 파이프라인의 흐름

```
RTSPSource → YoloDetect → RTSPPublish
(영상 입력)  (객체 감지)   (결과 송출)
```

### 최소 코드

```python
from pathlib import Path
from pipeworks import Pipeline
from pipeworks.embedded import RTSPSource, YoloDetect, RTSPPublish

# 1. 파이프라인 생성 (YAML 설정 파일 지정)
pipeline = Pipeline("my-pipeline", config=Path("config.yaml"))

# 2. Step 순차 추가
pipeline.step(RTSPSource(url="rtsp://camera/main"))
pipeline.step(YoloDetect(model_path=Path("models/yolo11n.pt")))
pipeline.step(RTSPPublish(url="rtsp://mediamtx:8554/{stream_id}"))

# 3. 실행
pipeline.run()
```

### config.yaml (YAML 설정)

```yaml
RTSPSource:
  reconnect: true
  reconnect_interval: 3
  transport: tcp
  timeout: 5

YoloDetect:
  classes: null  # null = 모든 클래스
  confidence: 0.25
  gpu_id: 0
  inference_interval: 1

RTSPPublish:
  bitrate: "5000k"
  framerate: 30
```

---

## 📚 핵심 개념

### Step
파이프라인의 기본 단위입니다. 입력 스트림을 받아 처리 후 출력합니다.

```python
class Step(ABC):
    def configure(self, config: SimpleNamespace) -> None:
        """YAML 설정을 적용합니다."""
        pass
    
    def process(self, inputs: Iterator[PipelineContext]) -> Iterator[PipelineContext]:
        """입력을 받아 처리 후 출력합니다."""
        pass
```

**Step의 종류:**
- **Source Step** (RTSPSource): 영상을 읽어들임
- **Processing Step** (YoloDetect, CustomProcessor): 데이터 처리
- **Sink Step** (RTSPPublish, Sink): 결과를 출력/저장

### PipelineContext
스트림의 각 "프레임" 또는 "패킷" 단위 데이터입니다.

```python
# Source Step에서 생성
context = PipelineContext(
    video_stream=stream,
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

### Source Step (스트림 입력)

#### **RTSPSource**
RTSP 카메라에서 영상을 읽습니다.

- **역할**: RTSP 스트림 수신 및 디코딩
- **사용**: `pipeline.step(RTSPSource(url="rtsp://camera/main"))`
- **설정**: `reconnect`, `reconnect_interval`, `transport`, `timeout`
- **상세**: [docs/pipeworks/embedded/rtsp_source.md](docs/pipeworks/embedded/rtsp_source.md)

---

### Processing Step (데이터 처리)

#### **YoloDetect**
각 프레임마다 YOLO로 객체 감지합니다 (동기).

- **역할**: 객체 감지 (동기 처리, GPU 활용)
- **사용**: `pipeline.step(YoloDetect(model_path=Path("models/yolo11n.pt")))`
- **설정**: `classes`, `confidence`, `gpu_id`, `inference_interval`
- **상세**: [docs/pipeworks/embedded/yolo_detect.md](docs/pipeworks/embedded/yolo_detect.md)

#### **YoloDetectBatch**
여러 프레임을 묶어 배치 YOLO 처리합니다.

- **역할**: 객체 감지 (배치 처리, 높은 처리량)
- **사용**: `pipeline.step(YoloDetectBatch(model_path=Path("models/yolo11n.pt")))`
- **설정**: `classes`, `confidence`, `gpu_id`, `batch_size`, `batch_timeout_ms`
- **상세**: [docs/pipeworks/embedded/yolo_detect_batch.md](docs/pipeworks/embedded/yolo_detect_batch.md)

#### **NvidiaDecode**
NVIDIA GPU를 이용해 RTSP 패킷을 디코딩합니다.

- **역할**: 하드웨어 가속 비디오 디코딩
- **사용**: `pipeline.step(NvidiaDecode())`
- **설정**: `max_surfaces`, `timeout_ms`
- **상세**: [docs/pipeworks/embedded/nvidia_decode.md](docs/pipeworks/embedded/nvidia_decode.md)

#### **StreamReport**
파이프라인 성능 지표를 수집합니다 (수신율, 추론 시간 등).

- **역할**: 성능 모니터링 및 로깅
- **사용**: `pipeline.step(StreamReport())`
- **설정**: 없음 (자동 수집)
- **상세**: [docs/pipeworks/embedded/stream_report.md](docs/pipeworks/embedded/stream_report.md)

---

### Sink Step (결과 출력)

#### **RTSPPublish**
처리된 영상을 RTSP로 발행합니다.

- **역할**: RTSP 스트림 발행 (인코딩 및 전송)
- **사용**: `pipeline.step(RTSPPublish(url="rtsp://mediamtx:8554/{stream_id}"))`
- **설정**: `bitrate`, `framerate`, `codec`
- **상세**: [docs/pipeworks/embedded/rtsp_publish.md](docs/pipeworks/embedded/rtsp_publish.md)

#### **NvidiaEncode**
NVIDIA GPU를 이용해 영상을 인코딩합니다.

- **역할**: 하드웨어 가속 비디오 인코딩
- **사용**: `pipeline.step(NvidiaEncode())`
- **설정**: `bitrate`, `framerate`, `codec`
- **상세**: [docs/pipeworks/embedded/nvidia_encode.md](docs/pipeworks/embedded/nvidia_encode.md)

#### **Sink**
처리된 데이터를 수신하고 최종 처리합니다.

- **역할**: 파이프라인 종료점 (커스텀 후처리)
- **사용**: `pipeline.step(Sink(step=MyFinalStep()))`
- **설정**: Step별로 상이
- **상세**: [docs/pipeworks/embedded/sink.md](docs/pipeworks/embedded/sink.md)

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
| **LocalYolo** | 로컬 YOLO 모델 로드 (유틸) | [docs/pipeworks/local_yolo.md](docs/pipeworks/local_yolo.md) |

### Embedded Step 문서

| Step | 문서 |
|------|------|
| RTSPSource | [docs/pipeworks/embedded/rtsp_source.md](docs/pipeworks/embedded/rtsp_source.md) |
| YoloDetect | [docs/pipeworks/embedded/yolo_detect.md](docs/pipeworks/embedded/yolo_detect.md) |
| YoloDetectBatch | [docs/pipeworks/embedded/yolo_detect_batch.md](docs/pipeworks/embedded/yolo_detect_batch.md) |
| RTSPPublish | [docs/pipeworks/embedded/rtsp_publish.md](docs/pipeworks/embedded/rtsp_publish.md) |
| NvidiaDecode | [docs/pipeworks/embedded/nvidia_decode.md](docs/pipeworks/embedded/nvidia_decode.md) |
| NvidiaEncode | [docs/pipeworks/embedded/nvidia_encode.md](docs/pipeworks/embedded/nvidia_encode.md) |
| Sink | [docs/pipeworks/embedded/sink.md](docs/pipeworks/embedded/sink.md) |
| StreamReport | [docs/pipeworks/embedded/stream_report.md](docs/pipeworks/embedded/stream_report.md) |

---

## 🚀 실제 예제들

### 예제 1: RTSP → YOLO 객체 감지 → RTSP 발행

```python
from pathlib import Path
from pipeworks import Pipeline
from pipeworks.embedded import RTSPSource, YoloDetect, RTSPPublish

pipeline = Pipeline("rtsp-yolo-pipeline", config=Path("config.yaml"))
pipeline.step(RTSPSource(url="rtsp://camera/main"))
pipeline.step(YoloDetect(model_path=Path("models/yolo11n.pt")))
pipeline.step(RTSPPublish(url="rtsp://mediamtx:8554/{stream_id}"))
pipeline.run()
```

**config.yaml:**
```yaml
RTSPSource:
  reconnect: true
  reconnect_interval: 3

YoloDetect:
  confidence: 0.5
  gpu_id: 0

RTSPPublish:
  bitrate: "5000k"
  framerate: 30
```

---

### 예제 2: 여러 RTSP 카메라 동시 처리

```python
from pathlib import Path
from pipeworks import Pipeline
from pipeworks.embedded import RTSPSource, YoloDetect, StreamReport, RTSPPublish

# 각 카메라별로 독립적인 파이프라인 생성
cameras = [
    ("cam01", "rtsp://camera1/main"),
    ("cam02", "rtsp://camera2/main"),
]

for cam_id, cam_url in cameras:
    pipeline = Pipeline(f"pipeline-{cam_id}", config=Path("config.yaml"))
    pipeline.step(RTSPSource(url=cam_url))
    pipeline.step(YoloDetect(model_path=Path("models/yolo11n.pt")))
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
            if context.detections is not None:
                # confidence 필터링
                filtered = [
                    det for det in context.detections.boxes.conf
                    if det >= self.min_confidence
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
from pathlib import Path
from pipeworks import Pipeline
from pipeworks.embedded import RTSPSource, YoloDetect, RTSPPublish
from my_filter import MyFilter

pipeline = Pipeline("live-dev-pipeline", config=Path("config.yaml"))
pipeline.step(RTSPSource(url="rtsp://camera/main"))
pipeline.step(YoloDetect(model_path=Path("models/yolo11n.pt")))
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

### 최소 필수

```bash
pip install pipeworks
```

### RTSP/영상 처리 포함

```bash
pip install pipeworks[av]
```

### YOLO 객체 감지 포함

```bash
pip install pipeworks[yolo,av]
```

### NVIDIA GPU 지원 포함

```bash
pip install pipeworks[yolo,av,nvidia]
```

### 전체 설치

```bash
pip install pipeworks[all]
```

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
  reconnect_interval: 5  # 초 단위
  timeout: 10
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
