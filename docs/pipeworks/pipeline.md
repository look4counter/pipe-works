# Pipeline: 파이프라인 조립 및 실행

전체 파이프라인을 선언하고 실행하는 메인 인터페이스입니다.

**파일 위치:** `src/pipeworks/pipeline.py`

---

## 📚 개요

Pipeline 클래스는:
- Step들을 순차 연결하는 **빌더 패턴** 제공
- YAML 설정 파일 로드 및 적용
- 파이프라인 실행 (로컬 또는 중앙 서버)
- 실행 중 설정 변경 감지 (Hotswap)

---

## 🔑 Pipeline 클래스

### 생성

```python
from pathlib import Path
from pipeworks import Pipeline

# 기본 생성
pipeline = Pipeline(
    name="my-pipeline",
    config=Path("config.yaml")
)
```

#### 파라미터

- **name** (str): 파이프라인 이름 (로그, 식별용)
- **config** (Path): YAML 설정 파일 경로

### Step 등록

#### step() 메서드

```python
pipeline = Pipeline("my-pipeline", config=Path("config.yaml"))
pipeline.step(RTSPSource(url="rtsp://camera"))
pipeline.step(YoloDetect(model_path=Path("models/yolo11n.pt")))
pipeline.step(RTSPPublish(url="rtsp://mediamtx:8554/{stream_id}"))
```

**메서드 체이닝 지원:**
```python
(Pipeline("pipeline", config=Path("config.yaml"))
    .step(RTSPSource(url="rtsp://camera"))
    .step(YoloDetect(model_path=Path("models/yolo11n.pt")))
    .step(RTSPPublish(url="rtsp://mediamtx:8554/output"))
)
```

#### Step 등록 순서 규칙

1. **첫 번째 Step은 Source**: 데이터 입력
2. **중간 Step들**: 데이터 처리
3. **마지막 Step은 Sink**: 데이터 출력

```python
# ✅ 올바른 구조
pipeline.step(RTSPSource(...))        # Source (입력)
pipeline.step(YoloDetect(...))        # Processing
pipeline.step(StreamReport(...))      # Processing
pipeline.step(RTSPPublish(...))       # Sink (출력)

# ❌ 잘못된 구조
pipeline.step(RTSPPublish(...))       # X: Sink가 먼저 와야 함
pipeline.step(RTSPSource(...))        # X: Source가 먼저 와야 함
```

### 실행

#### run() 메서드

```python
# 파이프라인 실행 (블로킹)
pipeline.run()
```

**동작:**
- 모든 Step을 순차 연결
- 소스에서 데이터를 읽기 시작
- 각 Step을 거쳐 처리
- Sink까지 전달
- 소스가 끝나면 파이프라인 종료

**중단 방법:**
```python
try:
    pipeline.run()
except KeyboardInterrupt:
    print("파이프라인이 중단되었습니다.")
```

---

## 📝 YAML 설정 파일

### 구조

```yaml
# config.yaml
SectionName:
  key1: value1
  key2: value2

RTSPSource:
  reconnect: true
  timeout_ms: 5000

YoloDetect:
  confidence: 0.5
  gpu_id: 0

RTSPPublish:
  bitrate: "5000k"
```

### 설정 로드 및 적용

파이프라인 시작 시:

1. Pipeline이 YAML 파일 로드
2. 각 Step의 이름(클래스명)으로 해당 섹션 찾기
3. `step.configure(config)` 호출

```python
# config.yaml에서:
# MyCustomStep:
#   param1: value1

# Step 클래스에서:
class MyCustomStep(Step):
    def configure(self, config: SimpleNamespace) -> None:
        # config는 YAML의 MyCustomStep 섹션
        self.param1 = getattr(config, 'param1', 'default')
```

### 실행 중 설정 변경 (Hotswap)

YAML 파일을 저장하면 자동으로:

1. 파이프라인이 변경 감지
2. 변경된 Step에 `configure()` 다시 호출
3. 실행 중인 Step의 설정 업데이트

```yaml
# 초기 설정
YoloDetect:
  confidence: 0.25

# 실행 중 수정 → 저장
YoloDetect:
  confidence: 0.5  # 자동으로 반영됨
```

---

## 🔄 동작 흐름

```
파이프라인 시작
    ↓
config.yaml 로드
    ↓
각 Step에 configure() 호출
    ↓
Source Step 시작 (입력 시작)
    ↓
각 데이터가 Step 체인을 통과
    - 각 Step의 process() 호출
    - context 변환 및 전달
    ↓
Sink Step에서 최종 처리
    ↓
Source 끝
    ↓
파이프라인 종료
```

---

## 🎯 실제 예제

### 예제 1: 기본 파이프라인

**pipeline.py:**
```python
from pathlib import Path
from pipeworks import Pipeline
from pipeworks.embedded import RTSPSource, YoloDetect, RTSPPublish

pipeline = Pipeline("basic-pipeline", config=Path("config.yaml"))
pipeline.step(RTSPSource(url="rtsp://camera/main"))
pipeline.step(YoloDetect(model_path=Path("models/yolo11n.pt")))
pipeline.step(RTSPPublish(url="rtsp://mediamtx:8554/output"))

if __name__ == "__main__":
    pipeline.run()
```

**config.yaml:**
```yaml
RTSPSource:
  reconnect: true
  reconnect_interval: 3
  transport: tcp
  timeout_ms: 5000

YoloDetect:
  classes: null
  confidence: 0.25
  gpu_id: 0
  inference_interval: 1

RTSPPublish:
  bitrate: "5000k"
  framerate: 30
```

**실행:**
```bash
python pipeline.py
```

### 예제 2: Custom Step과 함께

**my_processor.py:**
```python
from types import SimpleNamespace
from typing import Iterator
from pipeworks.models import PipelineContext, Step
import logging

logger = logging.getLogger(__name__)

class MyProcessor(Step):
    def __init__(self):
        self.enabled = True
    
    def configure(self, config: SimpleNamespace) -> None:
        self.enabled = getattr(config, 'enabled', True)
    
    def process(self, inputs: Iterator[PipelineContext]) -> Iterator[PipelineContext]:
        for context in inputs:
            if self.enabled and hasattr(context, 'detections'):
                count = len(context.detections)
                logger.info(f"감지된 객체: {count}")
                context.detection_count = count
            yield context
```

**config.yaml:**
```yaml
RTSPSource:
  reconnect: true
  timeout_ms: 5000

MyProcessor:
  enabled: true

YoloDetect:
  confidence: 0.5
  gpu_id: 0

RTSPPublish:
  bitrate: "5000k"
```

**pipeline.py:**
```python
from pathlib import Path
from pipeworks import Pipeline
from pipeworks.embedded import RTSPSource, YoloDetect, RTSPPublish
from my_processor import MyProcessor

pipeline = Pipeline("custom-pipeline", config=Path("config.yaml"))
pipeline.step(RTSPSource(url="rtsp://camera"))
pipeline.step(YoloDetect(model_path=Path("models/yolo11n.pt")))
pipeline.step(MyProcessor())
pipeline.step(RTSPPublish(url="rtsp://mediamtx:8554/output"))

if __name__ == "__main__":
    pipeline.run()
```

### 예제 3: 다중 파이프라인 (멀티 카메라)

```python
import threading
from pathlib import Path
from pipeworks import Pipeline
from pipeworks.embedded import RTSPSource, YoloDetect, StreamReport, RTSPPublish

def create_pipeline(cam_id: str, cam_url: str):
    pipeline = Pipeline(f"pipeline-{cam_id}", config=Path("config.yaml"))
    pipeline.step(RTSPSource(url=cam_url))
    pipeline.step(YoloDetect(model_path=Path("models/yolo11n.pt")))
    pipeline.step(StreamReport())
    pipeline.step(RTSPPublish(url=f"rtsp://mediamtx:8554/{cam_id}"))
    return pipeline

if __name__ == "__main__":
    cameras = [
        ("cam01", "rtsp://camera1/main"),
        ("cam02", "rtsp://camera2/main"),
        ("cam03", "rtsp://camera3/main"),
    ]
    
    threads = []
    for cam_id, cam_url in cameras:
        pipeline = create_pipeline(cam_id, cam_url)
        thread = threading.Thread(
            target=pipeline.run,
            name=cam_id,
            daemon=True
        )
        thread.start()
        threads.append(thread)
    
    # 메인 스레드 유지
    try:
        for thread in threads:
            thread.join()
    except KeyboardInterrupt:
        print("모든 파이프라인 중단 중...")
```

---

## 🛠️ 심화 사용법

### 설정 파일 없이 파이프라인 생성

임시 설정만 필요할 경우:

```python
from pathlib import Path
from pipeworks import Pipeline
from pipeworks.embedded import RTSPSource, RTSPPublish

# 임시 config.yaml 생성
config_content = """
RTSPSource:
  timeout_ms: 5000
RTSPPublish:
  bitrate: "5000k"
"""

config_path = Path("/tmp/config.yaml")
config_path.write_text(config_content)

pipeline = Pipeline("temp-pipeline", config=config_path)
pipeline.step(RTSPSource(url="rtsp://camera"))
pipeline.step(RTSPPublish(url="rtsp://mediamtx:8554/output"))
pipeline.run()
```

### 에러 처리

```python
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

pipeline = Pipeline("error-handling", config=Path("config.yaml"))
pipeline.step(RTSPSource(url="rtsp://camera"))
pipeline.step(YoloDetect(model_path=Path("models/yolo11n.pt")))
pipeline.step(RTSPPublish(url="rtsp://mediamtx:8554/output"))

try:
    pipeline.run()
except RuntimeError as e:
    logger.error(f"파이프라인 실행 오류: {e}")
except KeyboardInterrupt:
    logger.info("사용자 중단")
except Exception as e:
    logger.exception(f"예상 못한 오류: {e}")
```

---

## 🔗 관련 문서

- [Models](models.md): PipelineContext와 Step 정의
- [Hotswap](hotswap.md): 실행 중 코드/설정 재로드
- [Main](main.md): 중앙 스트림 프로세싱
- [Embedded Steps](../embedded/): 내장 Step들

---

## 💡 TIP

1. **config.yaml 경로**: 상대경로는 현재 작업 디렉토리 기준
2. **Step 이름**: 클래스명과 YAML 섹션명이 정확히 같아야 함
3. **Hotswap**: 파이프라인이 실행 중일 때도 config.yaml 수정 가능
4. **로깅**: `logging.basicConfig()` 로 수준 조정 가능
