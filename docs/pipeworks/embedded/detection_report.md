# YoloReport: 모든 backend의 처리 구간 보고

`YoloReport` 하나로 `YoloInference`의 모든 backend를 측정합니다. `CudaAsync`를 사용하면 Report는 래퍼 바깥에 연결합니다.

```python
from pipeworks import Backend
from pipeworks.embedded import CudaAsync, YoloInference, YoloReport

pipeline.step(CudaAsync(
    preprocess_step,
    YoloInference("models/yolo11n.plan", backend=Backend.TENSORRT, batch=True),
    postprocess_step,
    timeout_ms=20,
))
pipeline.step(YoloReport())
```

## backend별 통계

모든 backend는 같은 프로파일·실행 범위 저장소를 사용하고 표본은 종류별로 구분합니다. 기존 감지는 `YOLO`, 통합 추론은 `ULTRALYTICS`, `TORCHSCRIPT`, `TensorRT`로 출력하며 사용자 실행부는 지정한 경로로 구분합니다. 한 Report가 모든 종류의 측정을 활성화하므로 backend별 Report를 추가할 필요가 없습니다.

## 측정 항목

전처리, 배치 큐 대기, 입력 동기화, 입력 결합, 모델 준비, 모델 실행, 후처리, 출력 복사, GPU 완료 대기, 기타 비용과 전체 시간을 표시합니다. CPU 구간의 경과 시간과 CUDA 이벤트가 준비된 구간의 GPU 시간을 최근 1초·10초 기준으로 출력합니다. 측정된 구간만 표시하며 미완료 GPU 이벤트를 기다리거나 별도 동기화를 추가하지 않습니다.

완료·간격 건너뜀·작업자 바쁨·타임아웃·오류·부분 종료 건수를 backend별로 표시합니다. 입력당 완료 표본은 한 번만 기록하고 늦은 비동기 완료는 호출자의 타임아웃과 구분합니다. Report가 없으면 측정용 이벤트를 생성하지 않습니다.

## 전후처리·공유 배치 연결

전처리 단계는 공통 프로파일을 준비하고 추론 단계가 실제 backend로 연결합니다. 후처리는 전처리·추론·후처리를 포함한 전체 표본을 완료합니다. 전후처리 클래스 이름이 달라도 실제 실행부에 한 번 기록합니다. 공유 배치 작업자는 요청별 측정 결과를 원래 실행 범위로 돌려보내며 다른 파이프라인의 통계를 섞지 않습니다.

추론 단계가 있는 `CudaAsync`의 busy/timeout은 그 backend로 분류합니다. 추론 없이 전후처리만 감싸면 해당 예제 계열을 기준으로 분류합니다. Report는 대기 중에도 주기적으로 출력하며 종료 시 마지막 결과를 출력하고 수집 활성 상태를 정리합니다.

`전체`는 감지 처리 구간을 뜻하며 인코딩·송출 시간은 포함하지 않습니다. 전체 영상 파이프라인 시간은 `StreamReport`와 함께 확인합니다.
