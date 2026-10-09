# 동기 단일 감지 단계 계약

`YoloDetect(model_path, *, batch=False)`는 불리언 batch 인자를 받는다. False는 아래 단일 경로를 유지한다. True는 자체 GPU 입력 복제·이벤트·신호·배치 통계 경로에서 local_yolo.infer에 직접 요청을 제출한다. 배치 실패는 빈 결과로 전달한다. 모델 동명 YAML의 max_batch_size와 밀리초 timeout은 배치 수집 설정이다. 기본 추론 설정과 입력 간격은 두 모드에서 동일하다. 별도 YoloDetectBatch 클래스와 모듈은 제거하며 이전 별칭은 제공하지 않는다.

배치용 GPU 복제를 제출한 뒤 `pipeworks.execution.release_input(ready_event=event)`을 호출한다. Async는 이 이벤트가 완료된 요청에만 타임아웃 복사를 생략한다. 신호는 선택 사항이며 Async 밖에서는 아무 동작도 하지 않는다. 신호 이후 배치 처리는 복사본만 사용하고 공유 원본 데이터에 다시 접근하지 않는다. 결과용 작업 컨텍스트 속성 갱신은 가능하다.

개별 모드의 process는 첫 프레임부터 지정 간격의 입력을 호출 스레드에서 동기 추론한다. 선택 입력은 모델 로드·GPU 결과 준비가 완료된 다음에 동일 객체로 전달한다. 간격으로 건너뛴 입력은 detections=None이다.

영상과 감지 텐서는 GPU에 유지한다. 결과 영상은 원본 해상도의 RGB float HWC 텐서이며 박스 좌표는 원본 해상도 기준이다. 빈 박스는 정상이다.

잘못된 입력, 모델 로드 또는 예측 오류는 호출자에게 전파한다. 실패한 실제 예측은 공통 추론 통계에 포함한다. 동명 YAML의 timeout은 읽지 않는다.

비동기가 필요하면 아래처럼 공통 Async를 조합한다.

```python
from pipeworks.embedded import Async, YoloDetect
pipeline.step(Async(YoloDetect(model_path), timeout_ms=5))
```

Async 조합은 공통 래퍼의 설정·입력 복사·사용 중 통과·늦은 결과 폐기 계약을 따른다. TensorRTInference의 기존 비동기 동작은 이번 변경으로 달라지지 않는다.
