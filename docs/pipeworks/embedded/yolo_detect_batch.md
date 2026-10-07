# YoloDetectBatch: 배치 YOLO 객체 감지

여러 프레임을 모아 한 번에 YOLO 모델을 실행합니다 (높은 처리량).

**파일 위치:** `src/pipeworks/embedded/yolo_detect_batch.py`  
**역할**: Processing Step (배치 처리)

---

## 📚 개요

- 동기 버전 (`YoloDetect`)과 달리 배치 처리로 높은 처리량
- GPU 활용도 개선
- 지연 증가 (배치 대기 시간)

---

## 🔑 사용법

```python
from pipeworks import Pipeline
from pipeworks.embedded import RTSPSource, YoloDetectBatch, RTSPPublish

pipeline = Pipeline("batch-pipeline", config=Path("config.yaml"))
pipeline.step(RTSPSource(url="rtsp://camera"))
pipeline.step(YoloDetectBatch(model_path=Path("models/yolov8n.pt")))
pipeline.step(RTSPPublish(url="rtsp://mediamtx:8554/output"))
pipeline.run()
```

---

## ⚙️ 설정 (config.yaml)

```yaml
YoloDetectBatch:
  confidence: 0.25           # 신뢰도 임계값
  classes: null              # 클래스 필터
  gpu_id: 0                  # GPU ID
  batch_size: 16             # 배치 크기
  batch_timeout_ms: 50       # 최대 대기 시간 (ms)
```

### 주요 옵션

| 옵션 | 설명 |
|------|------|
| batch_size | 한 번에 처리할 프레임 수 (크수록 빠르지만 메모리 증가) |
| batch_timeout_ms | 배치가 가득 찰 때까지 기다리는 최대 시간 |

---

## 🔄 처리 흐름

```
프레임 1 → 배치에 추가
프레임 2 → 배치에 추가
...
프레임 N (batch_size 도달)
    ↓
한 번에 모두 YOLO 추론
    ↓
결과를 각 프레임에 저장
    ↓
다음 Step으로 전달
```

---

## 🎯 비교: Sync vs Batch

| 항목 | YoloDetect (동기) | YoloDetectBatch (배치) |
|------|-----------------|----------------------|
| 처리 모드 | 프레임 순차 | 배치 병렬 |
| 처리량 | 낮음 | 높음 |
| 지연 | 낮음 | 높음 (배치 대기) |
| GPU 활용도 | 중간 | 높음 |
| 메모리 | 낮음 | 높음 |

**선택 기준:**
- **YoloDetect**: 낮은 지연 중요 (실시간 응용)
- **YoloDetectBatch**: 높은 처리량 중요 (대량 카메라)

---

## 🔗 관련 문서

- [YoloDetect](yolo_detect.md): 동기 버전
- [Pipeline](../pipeline.md): 파이프라인 조립
