# StreamReport: 파이프라인 성능 모니터링

각 단계가 기록한 실행별 통계를 읽어 성능 지표를 DEBUG 로그로 기록합니다. 로거 이름은 `pipeworks.embedded.stream_report`이며, INFO 이상에서는 통계 메시지가 표시되지 않습니다.

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
from pipeworks import Backend
from step.yolo_pre_process import YoloPreProcess
from step.yolo_post_process import YoloPostProcess

from pathlib import Path
from pipeworks import Pipeline
from pipeworks.embedded import (
    RTSPSource,
    YoloInference,
    StreamReport,
    RTSPPublish,
    NvidiaDecode,
    NvidiaEncode,
)

pipeline = Pipeline("pipeline", config=Path("config.yaml"))
pipeline.step(RTSPSource(url="rtsp://camera"))
pipeline.step(NvidiaDecode())
pipeline.step(YoloPreProcess()).step(YoloInference(model_path=Path("models/yolov8n.pt"), backend=Backend.ULTRALYTICS)).step(YoloPostProcess())
pipeline.step(StreamReport())  # 성능 자동 표시
pipeline.step(NvidiaEncode())
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

최신 기록은 약 100ms의 발행 지연 후 표시되며 OS 스케줄링 지연이 추가될 수 있습니다. 잠금은 기록과 발행 사이에 남습니다. StreamReport가 없는 파이프라인은 기록 함수에서 잠금·시계·이력 수집을 건너뜁니다. Hotswap·TapSkipIfBusy·CudaAsync에 감싼 보고자도 확인하며 TapSkipIfBusy은 실행별 수집 문맥을 전달합니다. 별도 감지 프로파일링은 유지합니다. 직접 검증용 report_scope는 기본적으로 수집을 활성화합니다.

입력이 중단되어도 별도 출력 스레드가 현재 시각으로 표본 만료와 수신·송신 상태를 계산해 약 1초마다 표시합니다. 다른 보고자의 조회가 통계를 소모하지 않습니다. 출력 형식과 입력 컨텍스트 동일성은 유지합니다.

같은 환경의 작은 측정에서 기록 함수 4회 합계는 약 12.3µs에서 1.4µs로 줄었고, 수집 비활성 상태는 약 0.27µs였습니다. 프레임·추론 표본 각 600개의 발행은 약 4.9µs였습니다. 전체 처리량 개선률을 뜻하지 않으며 발행·조회 비용과 잠금 경합은 실제 부하에서 달라집니다. 출력·IPC 내부 동기화도 유지합니다.

---

## 로깅 설정

통계를 보려면 실행 프로세스에서 DEBUG 로그를 활성화합니다. StreamReport 자체는 핸들러나 전역 로그 수준을 설정하지 않습니다.

~~~python
import logging

logging.basicConfig(level=logging.DEBUG)
~~~

이미 핸들러가 설정되어 있다면 해당 핸들러의 수준도 DEBUG 메시지를 허용해야 합니다. 중앙 프로세스로 실행하는 파이프라인도 호출자의 로그 수준을 요청에 전달하고 호출자 핸들러로 기록합니다. 기존 지표 요약과 세부 단계의 두 줄 메시지 및 약 1초 보고 주기는 유지합니다.

## ⚙️ 설정 (config.yaml)

```yaml
StreamReport: {}  # 이 섹션은 생략해도 됩니다.
```

---

## 🔗 관련 문서

- [Pipeline](../pipeline.md): 파이프라인 조립
- [Models](../models.md): PipelineContext 구조

## 공개 API와 입출력 계약

`StreamReport()`는 생성자 옵션이 없고 configure는 전달된 설정을 사용하지 않습니다. 특정 컨텍스트 필드를 요구하거나 추가하지 않으며 같은 입력 객체를 그대로 출력합니다. 약 1초마다 수신·송신 상태, FPS, 프레임 처리·추론의 1초/최근 10초 평균을 표시하고 기록된 입력 대기·배치 대기·인코딩·송출 구간도 표시합니다.

프레임 처리 시간은 NvidiaDecode가 큐에서 꺼낸 processing_started_at부터 NvidiaEncode의 Encode 호출 완료까지이며 카메라 촬영부터의 시간이 아닙니다. 통계 수집 여부는 Pipeline의 실행 범위에서 결정합니다. 보고 Step만으로 모든 사용자 단계가 자동 측정되는 것은 아닙니다. 종료 시 출력 스레드를 멈추고 기다리며 YoloReport와 달리 마지막 결과를 별도로 출력하지 않습니다.

## 일반 보고 오류

부가 통계·마지막 로그 출력 실패는 경고를 남기고 생략하여 영상 전달을 종료하지 않습니다.
