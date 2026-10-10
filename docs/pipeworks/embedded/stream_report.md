# StreamReport: 파이프라인 성능 모니터링

각 단계가 기록한 실행별 통계를 읽어 성능 지표를 출력합니다.

**파일 위치:** `src/pipeworks/embedded/stream_report.py`  
**역할**: Processing Step (모니터링)

---

## 📚 개요

- 불변 통계 스냅샷을 읽어 성능 지표 표시
- 수신·송신 상태, 추론 시간, FPS 등 출력
- 별도 설정 불필요

---

## 🔑 사용법

```python
from pipeworks import Pipeline
from pipeworks.embedded import RTSPSource, YoloDetect, StreamReport, RTSPPublish

pipeline = Pipeline("pipeline", config=Path("config.yaml"))
pipeline.step(RTSPSource(url="rtsp://camera"))
pipeline.step(YoloDetect(model_path=Path("models/yolov8n.pt")))
pipeline.step(StreamReport())  # 성능 자동 표시
pipeline.step(RTSPPublish(url="rtsp://mediamtx:8554/output"))
pipeline.run()
```

---

## 📊 수집되는 지표

- **수신율**: 패킷 수신 성공 여부
- **추론 시간**: YOLO 모델 실행 시간
- **FPS**: 실제 처리 프레임 레이트
- **프레임 처리 시간**: 디코더 출력부터 인코더 호출 완료까지의 시간

## 읽기 전용 보고와 잠금 범위

통계 기록 함수는 기록 측 잠금 아래 누적값과 불변 스냅샷을 갱신합니다. StreamReport는 발행된 스냅샷 참조를 한 번 읽으며, 시작이나 주기 조회에서 통계 잠금을 획득하지 않습니다. 공유 카운터를 초기화하거나 공유 이력을 정리하지 않습니다.

1초 지표는 보고자별 이전 관측값과의 차이로 계산합니다. 최근 10초 평균은 정확한 `(현재-10초, 현재]`의 완료 표본을 대상으로 합니다. 이력은 초별 불변 청크의 합·개수를 공유하고 시간 경계 청크의 개별 표본만 확인합니다. 기록마다 전체 이력을 복사하지 않습니다.

입력이 중단되어도 별도 출력 스레드가 현재 시각으로 표본 만료와 수신·송신 상태를 계산해 약 1초마다 표시합니다. 다른 보고자의 조회가 통계를 소모하지 않습니다. 출력 형식과 입력 컨텍스트 동일성은 유지합니다.

제거한 잠금은 StreamReport의 통계 조회 잠금입니다. 여러 기록 스레드의 갱신 잠금과 출력·IPC 내부 동기화는 남습니다. 불변 스냅샷 생성 비용이 추가되므로 전체 처리량 개선 폭은 실제 부하에서 측정해야 합니다.

---

## ⚙️ 설정 (config.yaml)

```yaml
StreamReport:
  # 자동 표시 (별도 설정 불필요)
```

---

## 🔗 관련 문서

- [Pipeline](../pipeline.md): 파이프라인 조립
- [Models](../models.md): PipelineContext 구조
