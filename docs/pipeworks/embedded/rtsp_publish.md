# RTSPPublish: RTSP 스트림 발행

처리된 영상을 RTSP 서버로 발행합니다.

**파일 위치:** `src/pipeworks/embedded/rtsp_publish.py`  
**역할**: Sink Step (최종 출력)

---

## 📚 개요

- 처리된 영상을 RTSP로 인코딩 및 발행
- MediaMTX와 호환
- URL 템플릿 지원 (`{stream_id}` 치환)

---

## 🔑 사용법

```python
from pipeworks import Pipeline
from pipeworks.embedded import RTSPSource, YoloDetect, RTSPPublish

pipeline = Pipeline("rtsp-pipeline", config=Path("config.yaml"))
pipeline.step(RTSPSource(url="rtsp://camera"))
pipeline.step(YoloDetect(model_path=Path("models/yolov8n.pt")))
pipeline.step(RTSPPublish(url="rtsp://mediamtx:8554/{stream_id}"))
pipeline.run()
```

---

## ⚙️ 설정 (config.yaml)

```yaml
RTSPPublish:
  reconnect: true
  reconnect_interval: 3  # 초
  transport: tcp
  timeout_ms: 5000       # 밀리초
  packet_size: 1452
```

### 옵션 설명

| 옵션 | 설명 | 예제 |
|------|------|------|
| reconnect | 재연결 여부 | true |
| reconnect_interval | 재연결 간격(초) | 3 |
| transport | 전송 방식 | tcp, udp |
| timeout_ms | 제한 시간(밀리초, 기본값 5000) | 250, 5000, 10000 |
| packet_size | 패킷 크기 | 1452 |

기존 `timeout: 5`는 `timeout_ms: 5000`으로 변경해야 합니다. 0 이상의 유한한 숫자를 허용하며 이전 키는 오류로 처리합니다. 내부 FFmpeg 옵션에는 마이크로초로 변환하여 전달합니다.

---

## 📝 URL 템플릿

`{stream_id}`는 context의 stream_id로 치환됩니다.

```python
# context.stream_id = "cam01"
url="rtsp://mediamtx:8554/{stream_id}"
# → rtsp://mediamtx:8554/cam01

# 여러 카메라
url="rtsp://mediamtx:8554/output/{stream_id}/high"
# → rtsp://mediamtx:8554/output/cam01/high
```

---

## 🎯 실제 예제

### 다중 카메라 발행

```python
import threading
from pipeworks import Pipeline
from pipeworks.embedded import RTSPSource, YoloDetect, RTSPPublish

cameras = [
    ("cam01", "rtsp://192.168.1.10/main"),
    ("cam02", "rtsp://192.168.1.11/main"),
]

for cam_id, cam_url in cameras:
    pipeline = Pipeline(f"pipeline-{cam_id}", config=Path("config.yaml"))
    pipeline.step(RTSPSource(url=cam_url))
    pipeline.step(YoloDetect(model_path=Path("models/yolov8n.pt")))
    # 각 카메라별 경로로 발행
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
  bitrate: "5000k"
  framerate: 30
```

---

## 💡 TIP

1. **MediaMTX 설정**: RTSP 서버가 실행 중이어야 함
2. **비트레이트**: 낮을수록 빠르지만 화질 저하
3. **코덱 선택**: h264 (호환성), hevc (효율성)

---

## 🔗 관련 문서

- [RTSPSource](rtsp_source.md): RTSP 입력
- [Pipeline](../pipeline.md): 파이프라인 조립
