# NvidiaDecode: 하드웨어 비디오 디코딩

NVIDIA GPU를 사용해 RTSP 패킷을 디코딩합니다.

**파일 위치:** `src/pipeworks/embedded/nvidia_decode.py`  
**역할**: Processing Step (디코딩)

---

## 📚 개요

- NVIDIA GPU 하드웨어 가속 디코딩
- CPU 사용률 감소
- RTSPSource 다음에 배치 (선택사항)

---

## 🔑 사용법

```python
from pipeworks import Pipeline
from pipeworks.embedded import RTSPSource, NvidiaDecode, YoloDetect

pipeline = Pipeline("gpu-decode", config=Path("config.yaml"))
pipeline.step(RTSPSource(url="rtsp://camera"))
pipeline.step(NvidiaDecode())  # GPU 디코딩
pipeline.step(YoloDetect(model_path=Path("models/yolov8n.pt")))
pipeline.run()
```

---

## ⚙️ 설정 (config.yaml)

```yaml
NvidiaDecode:
  max_surfaces: 32            # CUDA surface 최대 개수
  timeout_ms: 5000            # 디코딩 타임아웃 (ms)
```

---

## 🔗 관련 문서

- [NvidiaEncode](nvidia_encode.md): 인코딩
- [RTSPSource](rtsp_source.md): RTSP 입력
- [Pipeline](../pipeline.md): 파이프라인 조립
