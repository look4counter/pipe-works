# LocalYolo: 로컬 YOLO 모델 관리

로컬 환경에서 YOLO 모델을 다운로드하고 캐시합니다.

**파일 위치:** `src/pipeworks/local_yolo.py`  
**용도**: YOLO 모델 관리 유틸리티

---

## 📚 개요

- YOLO 모델 자동 다운로드
- 로컬 캐시 관리
- 모델 경로 해석

---

## 🔑 사용법

### YOLO 모델 다운로드

```python
from pipeworks.local_yolo import download_yolo_model
from pathlib import Path

# yolov8n 모델 다운로드 (처음만)
model_path = download_yolo_model("yolov8n", cache_dir=Path("models"))

# 이후 동일 경로 반환 (캐시됨)
model_path = download_yolo_model("yolov8n", cache_dir=Path("models"))
```

### 파이프라인에서 사용

```python
from pathlib import Path
from pipeworks import Pipeline
from pipeworks.embedded import RTSPSource, YoloDetect, RTSPPublish
from pipeworks.local_yolo import download_yolo_model

# 모델 다운로드 (캐시됨)
model_path = download_yolo_model("yolov8n", cache_dir=Path("models"))

pipeline = Pipeline("yolo-pipeline", config=Path("config.yaml"))
pipeline.step(RTSPSource(url="rtsp://camera"))
pipeline.step(YoloDetect(model_path=model_path))
pipeline.step(RTSPPublish(url="rtsp://mediamtx:8554/output"))
pipeline.run()
```

---

## 📊 지원 모델

```
yolov8n   (6MB)    # nano - 가벼움
yolov8s   (22MB)   # small
yolov8m   (49MB)   # medium
yolov8l   (93MB)   # large
yolov8x   (161MB)  # extra-large
```

---

## 🔗 관련 문서

- [YoloDetect](embedded/yolo_detect.md): YOLO 객체 감지
- [YoloDetectBatch](embedded/yolo_detect_batch.md): 배치 감지
