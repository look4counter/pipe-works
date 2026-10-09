# 동기 단일 감지 단계 계약

생성자·configure 설정은 유지한다. process는 첫 프레임부터 지정 간격의 입력을 호출 스레드에서 동기 추론한다. 선택 입력은 모델 로드·GPU 결과 준비가 완료된 다음에 동일 객체로 전달한다. 간격으로 건너뛴 입력은 detections=None이다.

영상과 감지 텐서는 GPU에 유지한다. 결과 영상은 원본 해상도의 RGB float HWC 텐서이며 박스 좌표는 원본 해상도 기준이다. 빈 박스는 정상이다.

잘못된 입력, 모델 로드 또는 예측 오류는 호출자에게 전파한다. 실패한 실제 예측은 공통 추론 통계에 포함한다. 동명 YAML의 timeout은 읽지 않는다.

비동기가 필요하면 아래처럼 공통 Async를 조합한다.

```python
from pipeworks.embedded import Async, YoloDetect
pipeline.step(Async(YoloDetect(model_path), timeout_ms=5))
```

Async 조합은 공통 래퍼의 설정·입력 복사·사용 중 통과·늦은 결과 폐기 계약을 따른다. TensorRTInference의 기존 비동기 동작은 이번 변경으로 달라지지 않는다.
