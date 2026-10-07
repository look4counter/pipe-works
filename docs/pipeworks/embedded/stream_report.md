# StreamReport: 파이프라인 성능 모니터링

파이프라인의 성능 지표를 수집하고 기록합니다.

**파일 위치:** `src/pipeworks/embedded/stream_report.py`  
**역할**: Processing Step (모니터링)

---

## 📚 개요

- 자동 성능 지표 수집
- 수신율, 추론 시간, FPS 등 기록
- 별도 설정 불필요

---

## 🔑 사용법

```python
from pipeworks import Pipeline
from pipeworks.embedded import RTSPSource, YoloDetect, StreamReport, RTSPPublish

pipeline = Pipeline("pipeline", config=Path("config.yaml"))
pipeline.step(RTSPSource(url="rtsp://camera"))
pipeline.step(YoloDetect(model_path=Path("models/yolov8n.pt")))
pipeline.step(StreamReport())  # 성능 자동 수집
pipeline.step(RTSPPublish(url="rtsp://mediamtx:8554/output"))
pipeline.run()
```

---

## 📊 수집되는 지표

- **수신율**: 패킷 수신 성공 여부
- **추론 시간**: YOLO 모델 실행 시간
- **FPS**: 실제 처리 프레임 레이트
- **처리 지연**: end-to-end 지연 시간

---

## ⚙️ 설정 (config.yaml)

```yaml
StreamReport:
  # 자동 수집 (별도 설정 불필요)
```

---

## 🔗 관련 문서

- [Pipeline](../pipeline.md): 파이프라인 조립
- [Models](../models.md): PipelineContext 구조
