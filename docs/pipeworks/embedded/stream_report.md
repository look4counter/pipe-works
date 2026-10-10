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

통계 기록 함수는 기록 측 잠금 아래 누적값·단계별 합/건수와 최근 표본 deque만 갱신합니다. 매 기록마다 스냅샷이나 전체 단계 사전을 재생성하지 않습니다. 활성 보고자가 있을 때 프로세스 공용 발행 작업자 하나가 100ms마다 불변 스냅샷을 생성합니다. 마지막 보고자가 종료되면 발행 작업자도 정리합니다.

StreamReport는 발행된 스냅샷 참조를 한 번 읽으며, 보고자 초기화와 주기 조회에서 통계 잠금을 획득하지 않습니다. 공유 카운터를 초기화하거나 공유 이력을 정리하지 않습니다. 1초 지표는 보고자별 누적값 차분이고 FPS 분모는 관측한 스냅샷의 발행 시각 차이입니다. 최근 10초 평균은 발행된 표본 중 정확한 `(현재-10초, 현재]` 범위만 사용합니다. 이력을 tuple로 복사하는 비용은 발행 측에 있으며, 조회 계산은 최근 표본 수에 비례합니다.

최신 기록은 약 100ms의 발행 지연 후 표시되며 OS 스케줄링 지연이 추가될 수 있습니다. 잠금은 기록과 발행 사이에 남습니다. StreamReport가 없는 파이프라인은 기록 함수에서 잠금·시계·이력 수집을 건너뜁니다. Hotswap·Tap·CudaAsync에 감싼 보고자도 확인하며 Tap은 실행별 수집 문맥을 전달합니다. 별도 감지 프로파일링은 유지합니다. 직접 검증용 report_scope는 기본적으로 수집을 활성화합니다.

입력이 중단되어도 별도 출력 스레드가 현재 시각으로 표본 만료와 수신·송신 상태를 계산해 약 1초마다 표시합니다. 다른 보고자의 조회가 통계를 소모하지 않습니다. 출력 형식과 입력 컨텍스트 동일성은 유지합니다.

같은 환경의 작은 측정에서 기록 함수 4회 합계는 약 12.3µs에서 1.4µs로 줄었고, 수집 비활성 상태는 약 0.27µs였습니다. 프레임·추론 표본 각 600개의 발행은 약 4.9µs였습니다. 전체 처리량 개선률을 뜻하지 않으며 발행·조회 비용과 잠금 경합은 실제 부하에서 달라집니다. 출력·IPC 내부 동기화도 유지합니다.

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
