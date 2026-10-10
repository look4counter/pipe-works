# LocalYolo: 로컬 YOLO 모델 관리

## 공유 배치 추론의 경로 검사

`local_yolo.infer()`는 모델 작업자를 최초 준비할 때 경로를 정규화하고 파일 존재를 검사합니다. 같은 입력 경로를 다시 사용하면 캐시된 작업자를 바로 찾고 resolve/is_file을 생략합니다. 상대경로는 호출 작업 디렉터리별로 구분하며, 같은 정규 경로는 작업자를 공유합니다. 이미 로드된 모델은 파일 삭제 후에도 사용할 수 있고, 캐시된 링크의 대상 변경은 자동 재로드를 유발하지 않습니다.

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
- [YoloDetect](embedded/yolo_detect.md): 개별·공유 배치 감지
