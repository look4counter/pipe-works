# YoloDetect: 비동기 GPU YOLO 객체 감지

선택 프레임의 YOLO 추론을 별도 작업자와 CUDA 스트림에서 실행합니다. 추론이 지연되거나 실패해도 영상은 감지 결과 없이 계속 전달합니다.

입력은 설정된 GPU의 uint8 NV12 프레임이어야 합니다. 영상 변환·추론·좌표 복원을 GPU에서 수행하며 영상과 감지 텐서를 CPU로 복사하지 않습니다. `detections.orig_img`는 원본 해상도의 GPU RGB float 텐서이고 `detections.boxes.data`도 GPU에 남습니다. CPU 입력이나 GPU 번호 불일치는 오류를 기록하고 해당 프레임을 감지 결과 없이 전달합니다.

모델 초기화도 작업자에서 수행합니다. 선택 프레임은 모델 동명 YAML의 `timeout` 안에 완료된 결과만 받습니다. 제한 시간이 지나면 `detections=None`으로 전달하고 늦은 결과는 폐기합니다. 작업자가 사용 중이면 추가 추론을 쌓지 않고 프레임을 즉시 전달합니다. 입력 종료·반복자 닫기에서도 추론 완료를 기다리지 않습니다.

**파일 위치:** `src/pipeworks/embedded/yolo_detect.py`

---

## 📚 개요

- **역할**: Processing Step (데이터 처리)
- **기능**: 제한 시간이 있는 비동기 단일 프레임 YOLO 추론
- **의존성**: `torch`, `ultralytics`, `pyyaml`
- **GPU**: NVIDIA GPU 지원 (CUDA)
- **처리 모드**: 입력 순서를 유지하며 추론을 별도 작업자로 분리

---

## 🔑 사용법

### 기본 사용

```python
from pathlib import Path
from pipeworks import Pipeline
from pipeworks.embedded import RTSPSource, YoloDetect, RTSPPublish

pipeline = Pipeline("yolo-pipeline", config=Path("config.yaml"))
pipeline.step(RTSPSource(url="rtsp://camera"))
pipeline.step(YoloDetect(model_path=Path("models/yolov8n.pt")))
pipeline.step(RTSPPublish(url="rtsp://mediamtx:8554/output"))
pipeline.run()
```

---

## ⚙️ 설정 (config.yaml)

```yaml
YoloDetect:
  # 감지 설정
  confidence: 0.25              # 신뢰도 임계값 (0-1, 기본: 0.25)
  classes: null                 # 감지할 클래스 ID (null=모두, 기본: null)
  
  # 성능 튜닝
  gpu_id: 0                     # NVIDIA GPU ID (기본: 0)
  inference_interval: 1         # 추론 대상 선택 간격 (사용 중에는 건너뜀, 기본: 1)
```

### 각 옵션 설명

#### 모델 동명 YAML의 timeout

`models/yolo11n.pt`와 `models/yolo11n.engine`는 모두 `models/yolo11n.yml`을 읽습니다.

```yaml
timeout: 5  # 요청 제출부터 GPU 결과 준비까지 기다리는 최대 밀리초
```

파일이나 `timeout` 항목이 없으면 기본값은 5ms입니다. 0은 대기 없이 완료 여부만 확인합니다. 유한한 0 이상 숫자만 허용하며 불리언·문자열·음수는 설정 오류입니다. 배치용 `max_batch_size`가 함께 있어도 단일 단계에서는 사용하지 않습니다. `YoloDetectBatch`의 `timeout`은 배치 요청을 모으는 시간이고, 여기서는 해당 프레임의 결과 대기 제한입니다.

제한 시간은 실행 시작에 읽습니다. 처음 모델을 로드하거나 추론이 제한 시간보다 오래 걸리면 감지 결과 없이 전달되는 것이 정상입니다. 늦은 결과를 이후 프레임에 재사용하거나 이미 전달한 컨텍스트를 수정하지 않습니다. 실행 중인 요청은 최대 1개이며 CUDA 호출이 멈춰도 새 작업자를 계속 만들지 않습니다.

#### confidence (float)
신뢰도 임계값. 이 값 이상의 검출만 반환

```yaml
# 높은 신뢰도 (정확도 우선)
YoloDetect:
  confidence: 0.8

# 낮은 신뢰도 (감지량 우선)
YoloDetect:
  confidence: 0.25
```

#### classes (list[int] | null)
감지할 YOLO 클래스 ID만 필터링

```yaml
# 모든 클래스 감지 (기본)
YoloDetect:
  classes: null

# 사람(0)과 자동차(2)만 감지
YoloDetect:
  classes: [0, 2]

# 사람만 감지
YoloDetect:
  classes: [0]
```

**YOLO 기본 클래스:**
```
0: person
1: bicycle
2: car
3: motorcycle
...
```

#### gpu_id (int)
사용할 NVIDIA GPU 번호

```yaml
# GPU 0 사용 (기본)
YoloDetect:
  gpu_id: 0

# GPU 1 사용 (다중 GPU)
YoloDetect:
  gpu_id: 1
```

#### inference_interval (int)
몇 개 프레임마다 추론 대상을 선택할지 지정합니다. 선택 시점에 작업자가 사용 중이면 해당 프레임의 추론도 건너뜁니다.

```yaml
# 모든 프레임을 추론 대상으로 선택 (작업자 사용 중에는 건너뜀)
YoloDetect:
  inference_interval: 1

# 2개 프레임마다 처리 (2배 빠름, 감지 스킵)
YoloDetect:
  inference_interval: 2

# 5개 프레임마다 처리 (5배 빠름, 많은 감지 스킵)
YoloDetect:
  inference_interval: 5
```

---

## 📤 생성되는 PipelineContext 필드

```python
context.detections       # YOLO 감지 결과 (ultralytics.Results)
context.inference_time_ms  # 추론 소요 시간 (ms)
```

### 감지 결과 접근

```python
class MyResultStep(Step):
    def process(self, inputs: Iterator[PipelineContext]) -> Iterator[PipelineContext]:
        for context in inputs:
            if context.detections is not None:
                # 감지된 객체 수
                num_detections = len(context.detections)
                
                # 각 검출 정보
                boxes = context.detections.boxes      # 박스 좌표
                conf = context.detections.conf        # 신뢰도
                cls = context.detections.cls          # 클래스 ID
                
                for box, confidence, class_id in zip(boxes, conf, cls):
                    x1, y1, x2, y2 = box.xyxy[0]
                    logger.info(f"객체: 클래스={class_id}, 신뢰도={confidence:.2f}")
            
            yield context
```

---

## 🔄 처리 흐름

```
NvidiaDecode → GPU NV12 프레임
    ↓ (선택 프레임이며 작업자가 비어 있을 때만 제출)
GPU 복제 → 준비 이벤트 → 작업자 전용 CUDA 스트림
    ↓
GPU RGB 변환 → 추론 → 원본 좌표 복원 → 완료 이벤트
    ↓ (timeout 안에 준비된 결과만 해당 프레임에 연결)
GPU 감지 결과 또는 detections=None
    ↓
다음 Step으로 전달
```

---

## 🎯 실제 예제

### 예제 1: 사람만 감지

```yaml
YoloDetect:
  model_path: models/yolov8n.pt
  classes: [0]            # 사람(0)만
  confidence: 0.5
  gpu_id: 0
```

### 예제 2: 성능 최적화 (빠른 처리)

```yaml
YoloDetect:
  model_path: models/yolov8n.pt  # nano 모델 (가볍음)
  confidence: 0.25
  gpu_id: 0
  inference_interval: 3   # 3개 프레임마다만 추론
```

### 예제 3: 높은 정확도

```yaml
YoloDetect:
  model_path: models/yolov8m.pt  # medium 모델 (무거움)
  confidence: 0.75               # 높은 신뢰도
  gpu_id: 0
  inference_interval: 1          # 모든 프레임
```

### 예제 4: 완전한 파이프라인

```python
from pathlib import Path
from pipeworks import Pipeline
from pipeworks.embedded import (
    RTSPSource, YoloDetect, StreamReport, RTSPPublish
)

pipeline = Pipeline("full-pipeline", config=Path("config.yaml"))
pipeline.step(RTSPSource(url="rtsp://camera/main"))
pipeline.step(YoloDetect(model_path=Path("models/yolov8n.pt")))
pipeline.step(StreamReport())
pipeline.step(RTSPPublish(url="rtsp://mediamtx:8554/output"))
pipeline.run()
```

**config.yaml:**
```yaml
RTSPSource:
  reconnect: true
  timeout: 5

YoloDetect:
  confidence: 0.5
  gpu_id: 0
  inference_interval: 1

StreamReport:
  # 자동 수집

RTSPPublish:
  bitrate: "5000k"
  framerate: 30
```

---

## 🐛 트러블슈팅

### "CUDA out of memory"

GPU 메모리 부족

**해결:**
```yaml
YoloDetect:
  model_path: models/yolov8n.pt  # nano 모델로 변경
  inference_interval: 2          # 추론 빈도 감소
```

### "모델을 찾을 수 없음"

모델 경로가 잘못됨

**해결:**
```python
from ultralytics import YOLO

# 모델 다운로드
model = YOLO("yolov8n.pt")  # 자동 다운로드

# 또는 명시적으로 경로 지정
import Path
model_path = Path("models/yolov8n.pt")
assert model_path.exists(), f"모델 없음: {model_path}"
```

### "감지 결과가 None"

간격에 따른 건너뜀, 작업자 사용 중, 초기화·추론 시간 초과 또는 오류에서는 `None`이 정상입니다. 영상은 계속 전달됩니다. 오류는 로그를 확인하고, 정상 추론이 제한 시간을 넘는다면 모델 동명 YAML의 `timeout`을 조정합니다.

**해결:**
```python
# context.detections 확인 필수
if context.detections is not None:
    # 감지 결과 처리
else:
    # 감지 결과 없이 전달된 프레임
    pass
```

---

## 📊 성능 팁

| 모델 | 크기 | 정확도 | 속도 |
|------|------|--------|------|
| yolov8n | 6MB | 낮음 | 높음 |
| yolov8s | 22MB | 중간 | 중간 |
| yolov8m | 49MB | 높음 | 낮음 |
| yolov8l | 93MB | 매우 높음 | 매우 낮음 |

---

## 🔗 관련 문서

- [YoloDetectBatch](yolo_detect_batch.md): 배치 처리 (높은 처리량)
- [Pipeline](../pipeline.md): 파이프라인 조립
- [Models](../models.md): PipelineContext 구조
- [RTSPSource](rtsp_source.md): RTSP 입력
- [RTSPPublish](rtsp_publish.md): RTSP 발행

---

## 💡 TIP

1. **모델 선택**: 실시간 처리 필요하면 `yolov8n`, 정확도 중요하면 `yolov8m`
2. **신뢰도 조정**: Hotswap으로 `confidence` 값을 즉시 변경 가능
3. **프레임 스킵**: `inference_interval` 으로 처리량과 정확도 트레이드오프
4. **GPU 메모리**: 모니터링 도구로 메모리 사용량 확인
