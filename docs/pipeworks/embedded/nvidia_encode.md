# NvidiaEncode: 하드웨어 비디오 인코딩

NVIDIA GPU를 사용해 영상을 인코딩합니다.

**파일 위치:** `src/pipeworks/embedded/nvidia_encode.py`  
**역할**: Processing Step (인코딩)

---

## 📚 개요

- NVIDIA GPU 하드웨어 가속 인코딩
- CPU 사용률 감소
- RTSPPublish 전에 배치 (선택사항)

---

## 🔑 사용법

```python
from pipeworks import Pipeline
from pipeworks.embedded import RTSPSource, NvidiaEncode, RTSPPublish

pipeline = Pipeline("gpu-encode", config=Path("config.yaml"))
pipeline.step(RTSPSource(url="rtsp://camera"))
pipeline.step(NvidiaEncode())  # GPU 인코딩
pipeline.step(RTSPPublish(url="rtsp://mediamtx:8554/output"))
pipeline.run()
```

---

## ⚙️ 설정 (config.yaml)

```yaml
NvidiaEncode:
  bitrate: "5000k"            # 비트레이트
  framerate: 30               # 프레임 레이트
  codec: "h264"               # 코덱
```

---

## 🔗 관련 문서

- [NvidiaDecode](nvidia_decode.md): 디코딩
- [RTSPPublish](rtsp_publish.md): RTSP 발행
- [Pipeline](../pipeline.md): 파이프라인 조립
