# RTSPPublish: RTSP 스트림 발행

`packet`과 `video_stream`을 받은 뒤 압축 비디오 패킷을 RTSP 서버로 송출합니다. 원본 패킷 전달은 `RTSPSource → RTSPPublish`, GPU 처리 후 송출은 `RTSPSource → NvidiaDecode → 처리 단계 → NvidiaEncode → RTSPPublish`로 연결합니다.

**파일 위치:** `src/pipeworks/embedded/rtsp_publish.py`  
**역할**: Sink Step (최종 출력)

---

## 📚 개요

- 입력 스트림을 템플릿으로 연결을 열고 PyAV 패킷 송출
- MediaMTX와 호환
- 생성자에서 지정한 URL로 송출

---

## 🔑 사용법

```python
from pathlib import Path
from pipeworks import Pipeline
from pipeworks.embedded import RTSPSource, YoloDetect, RTSPPublish, NvidiaDecode, NvidiaEncode

pipeline = Pipeline("rtsp-pipeline", config=Path("config.yaml"))
pipeline.step(RTSPSource(url="rtsp://camera"))
pipeline.step(NvidiaDecode())
pipeline.step(YoloDetect(model_path=Path("models/yolov8n.pt")))
pipeline.step(NvidiaEncode())
pipeline.step(RTSPPublish(url="rtsp://mediamtx:8554/output"))
pipeline.run()
```

---

## ⚙️ 설정 (config.yaml)

```yaml
RTSPPublish:
  reconnect: true
  reconnect_interval_ms: 3000  # 밀리초
  transport: tcp
  timeout_ms: 5000       # 밀리초
  packet_size: 1452
```

### 옵션 설명

| 옵션 | 설명 | 예제 |
|------|------|------|
| reconnect | 재연결 여부 | true |
| reconnect_interval_ms | 재연결 간격(밀리초) | 3000 |
| transport | 전송 방식 | tcp, udp |
| timeout_ms | 제한 시간(밀리초, 기본값 5000) | 250, 5000, 10000 |
| packet_size | 패킷 크기 | 1452 |

기존 `reconnect_interval: 3`은 `reconnect_interval_ms: 3000`으로 변경해야 합니다. 0 이상의 유한한 숫자를 허용하며 불리언·문자열·음수·비유한 값과 이전 키는 오류로 처리합니다.

기존 `timeout: 5`는 `timeout_ms: 5000`으로 변경해야 합니다. 0 이상의 유한한 숫자를 허용하며 이전 키는 오류로 처리합니다. 내부 FFmpeg 옵션에는 마이크로초로 변환하여 전달합니다.

---

## 📝 송출 URL

송출 URL은 생성자에서 완성해 지정합니다. 컨텍스트의 속성으로 URL을 자동 치환하지 않습니다.

```python
cam_id = "cam01"
url = f"rtsp://mediamtx:8554/output/{cam_id}/high"
```

---

## 🎯 실제 예제

### 다중 카메라 발행

```python
from pathlib import Path
import threading
from pipeworks import Pipeline
from pipeworks.embedded import RTSPSource, YoloDetect, RTSPPublish, NvidiaDecode, NvidiaEncode

cameras = [
    ("cam01", "rtsp://192.168.1.10/main"),
    ("cam02", "rtsp://192.168.1.11/main"),
]

for cam_id, cam_url in cameras:
    pipeline = Pipeline(f"pipeline-{cam_id}", config=Path("config.yaml"))
    pipeline.step(RTSPSource(url=cam_url))
    pipeline.step(NvidiaDecode())
    pipeline.step(YoloDetect(model_path=Path("models/yolov8n.pt")))
    # 각 카메라별 경로로 발행
    pipeline.step(NvidiaEncode())
    pipeline.step(RTSPPublish(url=f"rtsp://mediamtx:8554/{cam_id}"))
    
    thread = threading.Thread(target=pipeline.run, daemon=True)
    thread.start()
```

**config.yaml:**
```yaml
RTSPSource:
  reconnect: true

YoloDetect:
  confidence: 0.5
  gpu_id: 0

RTSPPublish:
  transport: tcp
  timeout_ms: 5000
  packet_size: 1452
```

---

## 💡 TIP

1. **MediaMTX 설정**: RTSP 서버가 실행 중이어야 함
2. **인코딩 위치**: 프레임을 처리했으면 `NvidiaEncode`에서 패킷을 만든 뒤 송출
3. **스트림 형식**: 입력 스트림의 코덱·크기·시간 정보를 사용

---

## 🔗 관련 문서

- [RTSPSource](rtsp_source.md): RTSP 입력
- [Pipeline](../pipeline.md): 파이프라인 조립
