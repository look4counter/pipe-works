# RTSPSource: RTSP 스트림 입력

RTSP 카메라에서 영상을 받아 파이프라인에 공급합니다.

**파일 위치:** `src/pipeworks/embedded/rtsp_source.py`

---

## 📚 개요

- **역할**: Source Step (파이프라인의 입력)
- **기능**: RTSP 스트림 수신, 패킷 추출, 자동 재연결
- **의존성**: `av` (PyAV)
- **GPU**: 지원 안 함 (디코딩은 CPU)

---

## 🔑 사용법

### 기본 사용

```python
from pathlib import Path
from pipeworks import Pipeline
from pipeworks.embedded import RTSPSource

pipeline = Pipeline("rtsp-pipeline", config=Path("config.yaml"))
pipeline.step(RTSPSource(url="rtsp://192.168.1.100:554/stream1"))
pipeline.step(...)  # 다음 Step들
pipeline.run()
```

### 여러 카메라 처리

```python
import threading

cameras = [
    ("cam01", "rtsp://cam01/main"),
    ("cam02", "rtsp://cam02/main"),
]

for cam_id, cam_url in cameras:
    pipeline = Pipeline(f"pipeline-{cam_id}", config=Path("config.yaml"))
    pipeline.step(RTSPSource(url=cam_url))
    # ... 더 많은 Step
    
    thread = threading.Thread(target=pipeline.run, daemon=True)
    thread.start()
```

---

## ⚙️ 설정 (config.yaml)

```yaml
RTSPSource:
  # 재연결 설정
  reconnect: true                  # 연결 실패 시 재연결 (기본: true)
  reconnect_interval: 3            # 재연결 대기 시간 (초, 기본: 3)
  
  # 연결 설정
  transport: tcp                   # tcp 또는 udp (기본: tcp)
  timeout: 5                       # 연결/패킷 수신 타임아웃 (초, 기본: 5)
```

### 각 옵션 설명

#### reconnect (bool)
- `true`: 연결 실패/종료 시 자동 재연결
- `false`: 실패 시 파이프라인 중단

```yaml
# 항상 재연결 시도
RTSPSource:
  reconnect: true
  reconnect_interval: 10  # 10초 기다린 후 재연결

# 실패 시 즉시 종료
RTSPSource:
  reconnect: false
```

#### transport (str)
- `tcp`: TCP 프로토콜 (안정적, 느림)
- `udp`: UDP 프로토콜 (빠름, 불안정할 수 있음)

```yaml
# 안정적인 연결 (기본)
RTSPSource:
  transport: tcp

# 빠른 연결 (불안정 가능)
RTSPSource:
  transport: udp
```

#### timeout (float)
연결 및 패킷 수신 타임아웃 (초)

```yaml
# 빠른 타임아웃 (긴 지연 환경에서 안 됨)
RTSPSource:
  timeout: 3

# 넉넉한 타임아웃 (느린 네트워크)
RTSPSource:
  timeout: 15
```

---

## 📤 생성되는 PipelineContext

각 RTSP 패킷마다 PipelineContext를 생성합니다.

```python
context = PipelineContext(
    video_stream=av.VideoStream,    # 비디오 스트림 객체
    packet=av.Packet,               # H.264/H.265 패킷
    pixel_format="NV12",            # 픽셀 포맷 (하드웨어 디코딩 사용 시)
    # ... GPU 처리 관련 필드
)
```

### 필드 사용 예

```python
class MyProcessingStep(Step):
    def process(self, inputs: Iterator[PipelineContext]) -> Iterator[PipelineContext]:
        for context in inputs:
            # RTSPSource에서 제공
            video_stream = context.video_stream
            packet = context.packet
            
            # 비디오 정보 접근
            width = video_stream.codec_context.width
            height = video_stream.codec_context.height
            fps = video_stream.average_rate
            
            logger.info(f"해상도: {width}x{height}, FPS: {fps}")
            yield context
```

---

## 🔄 재연결 메커니즘

### 정상 재연결

```
RTSP 연결 시도
    ↓
[성공] → 패킷 수신 시작
    ↓
패킷 끝 (EOS 도달)
    ↓
reconnect=true → 대기 후 다시 시도
reconnect=false → 파이프라인 종료
```

### 에러 재연결

```
RTSP 연결 시도
    ↓
[실패] → FFmpegError 발생
    ↓
reconnect=true → 대기 후 다시 시도
reconnect=false → 파이프라인 중단 (RuntimeError)
```

---

## 🛠️ 실제 예제

### 예제 1: 기본 RTSP 입력

```python
from pathlib import Path
from pipeworks import Pipeline
from pipeworks.embedded import RTSPSource, StreamReport, Sink

# RTSP 소스에서 받아 로그에 기록만 함
pipeline = Pipeline("rtsp-basic", config=Path("config.yaml"))
pipeline.step(RTSPSource(url="rtsp://192.168.1.100:554/stream1"))
pipeline.step(StreamReport())
pipeline.step(Sink(step=MyLogStep()))
pipeline.run()
```

**config.yaml:**
```yaml
RTSPSource:
  reconnect: true
  reconnect_interval: 3
  timeout: 5
```

### 예제 2: 느린 네트워크 설정

```yaml
RTSPSource:
  reconnect: true
  reconnect_interval: 10        # 10초 대기
  transport: tcp                # TCP 안정성
  timeout: 15                   # 15초 타임아웃
```

### 예제 3: RTSP → YOLO → 결과 전송

```python
from pathlib import Path
from pipeworks import Pipeline
from pipeworks.embedded import RTSPSource, YoloDetect, RTSPPublish

pipeline = Pipeline("rtsp-yolo", config=Path("config.yaml"))
pipeline.step(RTSPSource(url="rtsp://camera/main"))
pipeline.step(YoloDetect(model_path=Path("models/yolo11n.pt")))
pipeline.step(RTSPPublish(url="rtsp://mediamtx:8554/output"))
pipeline.run()
```

**config.yaml:**
```yaml
RTSPSource:
  reconnect: true
  reconnect_interval: 3
  timeout: 5

YoloDetect:
  confidence: 0.5
  gpu_id: 0

RTSPPublish:
  bitrate: "5000k"
  framerate: 30
```

---

## 🐛 트러블슈팅

### "RTSP 입력에 비디오 스트림이 없습니다"

카메라가 비디오 스트림을 제공하지 않습니다.

**해결:**
- 카메라 설정 확인
- URL이 정확한지 확인
- 다른 RTSP 경로 시도 (e.g., `/stream1`, `/main`)

### "타임아웃" 또는 "연결 거부"

네트워크 연결 문제

**해결:**
```yaml
RTSPSource:
  timeout: 15           # 타임아웃 증가
  reconnect_interval: 5 # 재연결 간격 증가
```

### "계속 재연결 시도"

네트워크 불안정 또는 카메라 오프라인

**해결:**
- 카메라 상태 확인
- 네트워크 안정성 확인
- 재연결 비활성화하고 에러 처리:

```yaml
RTSPSource:
  reconnect: false  # 실패 시 즉시 종료
```

---

## 🔗 관련 문서

- [Pipeline](../pipeline.md): 파이프라인 조립
- [Models](../models.md): PipelineContext 구조
- [RTSPPublish](rtsp_publish.md): RTSP 발행
- [YoloDetect](yolo_detect.md): 객체 감지

---

## 💡 TIP

1. **URL 형식**: `rtsp://IP:PORT/path` (기본 포트: 554)
2. **실시간 지연 최소화**: `transport: tcp` + 짧은 `timeout`
3. **안정성 우선**: `reconnect: true` + 긴 `reconnect_interval`
4. **다중 카메라**: 각 카메라마다 별도의 `RTSPSource` Step 사용
