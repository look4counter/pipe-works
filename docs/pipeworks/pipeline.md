# Pipeline: 파이프라인 조립 및 실행

전체 파이프라인을 선언하고 실행하는 메인 인터페이스입니다.

**파일 위치:** `src/pipeworks/pipeline.py`

---

## 📚 개요

Pipeline 클래스는:
- Step들을 순차 연결하는 **빌더 패턴** 제공
- YAML 설정 파일 로드 및 적용
- Batch 추론 여부에 따라 호출자 또는 별칭으로 선택한 중앙 프로세스에서 실행
- 실행 중 설정 변경 감지 (Hotswap)

---

## 🔑 Pipeline 클래스

### 생성

```python
from pathlib import Path
from pipeworks import Pipeline

# 기본 생성
pipeline = Pipeline(name="my-pipeline", config=Path("config.yaml"))
```

#### 파라미터

- **name** (str): 파이프라인 이름 (로그, 식별용)
- **config** (Path): YAML 설정 파일 경로
- **batch_process** (str, 기본 `"production"`): Batch 실행의 중앙 프로세스 별칭입니다. 같은 별칭끼리 공유하며 다른 별칭은 분리합니다. 영문자·숫자·밑줄·하이픈 1~64자로 대소문자를 구분합니다. Batch 추론이 없으면 별칭과 관계없이 호출자 프로세스에서 실행합니다.

### Step 등록

#### step() 메서드

```python
from pipeworks import Backend
from step.yolo_pre_process import YoloPreProcess
from step.yolo_post_process import YoloPostProcess

pipeline = Pipeline("my-pipeline", config=Path("config.yaml"))
pipeline.step(RTSPSource(url="rtsp://camera"))
pipeline.step(NvidiaDecode())
pipeline.step(YoloPreProcess()).step(YoloInference(model_path=Path("models/yolo11n.pt"), backend=Backend.ULTRALYTICS)).step(YoloPostProcess())
pipeline.step(NvidiaEncode())
pipeline.step(RTSPPublish(url="rtsp://mediamtx:8554/output"))
```

**메서드 체이닝 지원:**
```python
from pipeworks import Backend
from step.yolo_pre_process import YoloPreProcess
from step.yolo_post_process import YoloPostProcess

(
    Pipeline("pipeline", config=Path("config.yaml"))
    .step(RTSPSource(url="rtsp://camera"))
    .step(NvidiaDecode())
    .step(YoloPreProcess()).step(YoloInference(model_path=Path("models/yolo11n.pt"), backend=Backend.ULTRALYTICS)).step(YoloPostProcess())
    .step(NvidiaEncode())
    .step(RTSPPublish(url="rtsp://mediamtx:8554/output"))
)
```

#### Step 등록 순서 규칙

1. **첫 번째 Step은 Source**: 데이터 입력
2. **중간 Step들**: 데이터 처리
3. **출력 Step**: 앞 단계의 출력 형식에 맞는 소비 단계를 연결합니다. `StreamReport`는 `RTSPPublish` 뒤에도 둘 수 있습니다.

```python
from pipeworks import Backend
from step.yolo_pre_process import YoloPreProcess
from step.yolo_post_process import YoloPostProcess

# ✅ 올바른 구조
pipeline.step(RTSPSource(...))  # Source (입력)
pipeline.step(NvidiaDecode())
pipeline.step(YoloPreProcess()).step(YoloInference(..., backend=Backend.ULTRALYTICS)).step(YoloPostProcess())  # Processing
pipeline.step(StreamReport(...))  # Processing
pipeline.step(NvidiaEncode())
pipeline.step(RTSPPublish(...))  # Sink (출력)

# ❌ 잘못된 구조
pipeline.step(RTSPPublish(...))  # X: 입력을 만드는 소스가 필요함
pipeline.step(RTSPSource(...))  # X: Source가 먼저 와야 함
```

### 실행

#### run() 메서드

```python
# 파이프라인 실행 (블로킹)
pipeline.run()

# Batch 추론을 등록한 경우 개발용 중앙 프로세스에서 실행
development_pipeline = Pipeline(
    "development", config=Path("config.yaml"), batch_process="development"
)
development_pipeline.run()
```

`run()`은 `YoloInference(batch=True)`가 하나라도 있으면 생성자의 `batch_process` 별칭에 해당하는 중앙 프로세스에서 전체 파이프라인을 실행합니다. `Hotswap`, `CudaAsync`, `EveryNFrames`, `TapSkipIfBusy` 내부도 검사합니다. Batch 추론이 없으면 호출자 프로세스에서 실행하며 직렬화와 중앙 연결을 생략합니다. 두 경로는 동일한 단계 실행·설정 감시 로직을 사용합니다. 기본 별칭은 `"production"`입니다. 같은 별칭은 프로세스와 모델 작업자를 공유하고 다른 별칭은 별도 프로세스를 사용합니다. 각 프로세스에서 모델을 별도로 로드하며 같은 GPU의 자원과 장치 전체 장애는 공유합니다. 기존 `development=True`는 `batch_process="development"`로 바꿉니다. 자세한 동작은 [중앙 프로세스](main.md)를 참고하세요.

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

### 생성자와 YAML의 우선순위

설정 가능한 내장 Step은 **YAML 값 → 생성자 값 → 기본값** 순서로 옵션을 선택합니다. YAML 섹션이나 옵션이 없으면 생성자 값을 사용합니다. 실행 중 YAML에서 옵션을 삭제하면 최초 생성자 값으로 돌아갑니다. YAML에 지정한 `0`, `false`, 빈 목록, `null`은 누락으로 취급하지 않으며 해당 옵션의 검증 규칙을 적용합니다. 설정 파일 자체가 없는 경우의 오류 처리는 기존과 같습니다.

```python
from pipeworks import Backend
inference = YoloInference(
    Path("model.engine"),
    backend=Backend.TENSORRT,
    gpu_id=2,
    profile_index=1,
)
pipeline.step(inference)
```

```yaml
YoloInference:
  backend: tensorrt
  profile_index: 0
```

위 설정에서는 `gpu_id=2`, `profile_index=0`이 적용됩니다. YAML에서 `profile_index`를 삭제하면 생성자 값인 `1`로 돌아갑니다. URL·모델 경로와 `batch`는 기존처럼 생성자에서 지정합니다.

적용 대상은 `RTSPSource`, `RTSPPublish`, `NvidiaDecode`, `NvidiaEncode`, `YoloInference`, `CudaAsync`, `EveryNFrames`입니다. `TapSkipIfBusy`은 내부 Step에 설정을 전달하고, `CudaAsync` 내부 Step은 기존처럼 최상위 클래스명 섹션으로 설정합니다.

사용자 정의 Step은 `configure()`와 `process()`를 반드시 구현하거나 구체 구현을 상속해야 합니다. 누락하면 생성 시 `TypeError`가 발생합니다. 설정이 필요 없으면 빈 `configure()`를 구현합니다. 같은 우선순위를 사용하려면 공통 지원을 다음처럼 적용할 수 있습니다. `_set_config_defaults()`는 생성자 값을 보관한 뒤 빈 설정으로 `configure()`를 호출하므로 필요한 상태를 먼저 초기화합니다.

```python
class CustomStep(Step):
    def __init__(self, *, threshold=0.5):
        self._set_config_defaults(threshold=threshold)

    def configure(self, config):
        config = self._resolve_config(config)
        self.threshold = config.threshold

    def process(self, inputs):
        yield from inputs
```

### 구조

```yaml
# config.yaml
SectionName:
  key1: value1
  key2: value2

RTSPSource:
  reconnect: true
  timeout_ms: 5000

YoloInference:
  backend: ultralytics
  gpu_id: 0

YoloPostProcess:
  confidence: 0.5

RTSPPublish:
  transport: tcp
  timeout_ms: 5000
  packet_size: 1452
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
        self.param1 = getattr(config, "param1", "default")

    def process(self, inputs):
        yield from inputs
```

### 실행 중 설정 변경 (Hotswap)

YAML 파일을 저장하면 자동으로:

1. 파이프라인이 변경 감지
2. 변경된 Step에 `configure()` 다시 호출
3. 실행 중인 Step의 설정 업데이트

코드와 YAML은 프로세스별 공유 OS 감시기를 사용합니다. 처리 경계에서 기본 0.5초 간격으로 변경 표시를 확인하고, 변경된 파일의 내용과 해시를 공유합니다. 변경이 없으면 파일 내용을 읽지 않습니다. 알림 누락은 30초 내용 재검사로 보완하며, 감시 실패 시 재등록과 0.5초 재검사로 이어갑니다. 잘못된 설정은 이전 설정을 유지합니다.

```yaml
# 초기 설정
YoloInference:
  backend: ultralytics


YoloPostProcess:
  confidence: 0.25

# 실행 중 수정 → 저장
YoloInference:
  backend: ultralytics


YoloPostProcess:
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
from pipeworks import Backend
from step.yolo_pre_process import YoloPreProcess
from step.yolo_post_process import YoloPostProcess

from pathlib import Path
from pipeworks import Pipeline
from pipeworks.embedded import (
    RTSPSource,
    YoloInference,
    RTSPPublish,
    NvidiaDecode,
    NvidiaEncode,
)

pipeline = Pipeline("basic-pipeline", config=Path("config.yaml"))
pipeline.step(RTSPSource(url="rtsp://camera/main"))
pipeline.step(NvidiaDecode())
pipeline.step(YoloPreProcess()).step(YoloInference(model_path=Path("models/yolo11n.pt"), backend=Backend.ULTRALYTICS)).step(YoloPostProcess())
pipeline.step(NvidiaEncode())
pipeline.step(RTSPPublish(url="rtsp://mediamtx:8554/output"))

if __name__ == "__main__":
    pipeline.run()
```

**config.yaml:**
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
  classes: null
  confidence: 0.25

RTSPPublish:
  transport: tcp
  timeout_ms: 5000
  packet_size: 1452
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
        self.enabled = getattr(config, "enabled", True)

    def process(self, inputs: Iterator[PipelineContext]) -> Iterator[PipelineContext]:
        for context in inputs:
            if self.enabled and hasattr(context, "detections"):
                count = sum(
                    len(result.boxes)
                    for result in (context.detections or {}).values()
                    if result is not None
                )
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

YoloInference:
  backend: ultralytics
  gpu_id: 0

YoloPostProcess:
  confidence: 0.5

RTSPPublish:
  transport: tcp
  timeout_ms: 5000
  packet_size: 1452
```

**pipeline.py:**
```python
from pipeworks import Backend
from step.yolo_pre_process import YoloPreProcess
from step.yolo_post_process import YoloPostProcess

from pathlib import Path
from pipeworks import Pipeline
from pipeworks.embedded import (
    RTSPSource,
    YoloInference,
    RTSPPublish,
    NvidiaDecode,
    NvidiaEncode,
)
from my_processor import MyProcessor

pipeline = Pipeline("custom-pipeline", config=Path("config.yaml"))
pipeline.step(RTSPSource(url="rtsp://camera"))
pipeline.step(NvidiaDecode())
pipeline.step(YoloPreProcess()).step(YoloInference(model_path=Path("models/yolo11n.pt"), backend=Backend.ULTRALYTICS)).step(YoloPostProcess())
pipeline.step(MyProcessor())
pipeline.step(NvidiaEncode())
pipeline.step(RTSPPublish(url="rtsp://mediamtx:8554/output"))

if __name__ == "__main__":
    pipeline.run()
```

### 예제 3: 다중 파이프라인 (멀티 카메라)

```python
from pipeworks import Backend
from step.yolo_pre_process import YoloPreProcess
from step.yolo_post_process import YoloPostProcess

import threading
from pathlib import Path
from pipeworks import Pipeline
from pipeworks.embedded import (
    RTSPSource,
    YoloInference,
    StreamReport,
    RTSPPublish,
    NvidiaDecode,
    NvidiaEncode,
)


def create_pipeline(cam_id: str, cam_url: str):
    pipeline = Pipeline(f"pipeline-{cam_id}", config=Path("config.yaml"))
    pipeline.step(RTSPSource(url=cam_url))
    pipeline.step(NvidiaDecode())
    pipeline.step(YoloPreProcess()).step(YoloInference(model_path=Path("models/yolo11n.pt"), backend=Backend.ULTRALYTICS)).step(YoloPostProcess())
    pipeline.step(StreamReport())
    pipeline.step(NvidiaEncode())
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
        thread = threading.Thread(target=pipeline.run, name=cam_id, daemon=True)
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

### 임시 설정 파일로 파이프라인 생성

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
  transport: tcp
  timeout_ms: 5000
  packet_size: 1452
"""

config_path = Path("config.temporary.yaml")
config_path.write_text(config_content, encoding="utf-8")

pipeline = Pipeline("temp-pipeline", config=config_path)
pipeline.step(RTSPSource(url="rtsp://camera"))
pipeline.step(RTSPPublish(url="rtsp://mediamtx:8554/output"))
pipeline.run()
```

### 에러 처리

```python
from pipeworks import Backend
from step.yolo_pre_process import YoloPreProcess
from step.yolo_post_process import YoloPostProcess

import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

pipeline = Pipeline("error-handling", config=Path("config.yaml"))
pipeline.step(RTSPSource(url="rtsp://camera"))
pipeline.step(NvidiaDecode())
pipeline.step(YoloPreProcess()).step(YoloInference(model_path=Path("models/yolo11n.pt"), backend=Backend.ULTRALYTICS)).step(YoloPostProcess())
pipeline.step(NvidiaEncode())
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
- [Embedded Steps](embedded/): 내장 Step들

---

## 💡 TIP

1. **config.yaml 경로**: 상대경로는 현재 작업 디렉토리 기준
2. **Step 이름**: 클래스명과 YAML 섹션명이 정확히 같아야 함
3. **Hotswap**: 파이프라인이 실행 중일 때도 config.yaml 수정 가능
4. **로깅**: `logging.basicConfig()` 로 수준 조정 가능

실행 간격은 [EveryNFrames](embedded/every_n_frames.md)의 `interval_frames`로 지정합니다. 래퍼 내부 단계도 각 클래스명 YAML 섹션을 사용하며 생성자 기본값과 실시간 변경을 유지합니다.

## 반환값과 배포 앱 사용

step(step)는 같은 Pipeline을 반환해 연결 등록을 이어갈 수 있습니다. run()은 블로킹 실행이며 프레임 목록이나 추론 결과를 반환하지 않고 정상 종료 시 None입니다. 결과는 사용자 Step에서 소비·저장합니다. 앱 진입점은 if __name__ == "__main__"으로 보호하고 설정·모델 경로는 앱 파일 기준 절대경로로 만듭니다.

생성자는 설정 파일을 즉시 읽으므로 파일을 먼저 준비해야 합니다. 일반 사용자 Step은 자동 Hotswap, 내장 Step은 코드 교체 없이 설정 감시를 적용합니다. config의 batch_process 키로 실행 그룹을 바꾸지 않으며 생성자 batch_process만 사용합니다. 로컬 실행의 오류는 원래 예외로, 중앙 실행의 오류는 전달된 메시지를 포함한 RuntimeError 등으로 보일 수 있습니다. 사용자 Step의 기본 오류 복구 범위는 [Hotswap](hotswap.md)을 참고하세요.

[별도 앱 만들기](getting_started.md), [설정 파일](configuration.md), [전체 모듈](README.md)을 함께 참고하세요.
