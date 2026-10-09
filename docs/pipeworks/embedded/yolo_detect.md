# YoloDetect: 동기 GPU YOLO 객체 감지

선택 프레임의 모델 로드·변환·추론·좌표 복원을 호출 스레드에서 동기로 실행한다. 입력 준비 이벤트를 기다리는 별도 CUDA 추론 스트림을 사용하며, GPU 결과가 준비된 다음에 같은 입력 컨텍스트를 전달한다. 내부 Python 작업자나 시간 제한은 없으며, 잘못된 입력·모델 로드·추론 오류는 호출자에게 예외로 전파한다.

입력은 설정된 GPU의 uint8 NV12 프레임이다. 영상과 감지 텐서를 CPU로 복사하지 않는다. 결과의 `orig_img`는 원본 해상도의 GPU RGB float HWC 텐서이며, `boxes.data`는 원본 좌표의 GPU 텐서이다. 빈 박스 결과도 정상이다.

## 사용법

```python
from pathlib import Path
from pipeworks.embedded import YoloDetect

pipeline.step(YoloDetect(Path("models/yolo11n.pt")))
```

`.pt`와 Ultralytics에서 지원하는 `.engine` 모델 경로를 사용할 수 있다. 모델은 입력 스트림의 첫 선택 프레임에서 준비하고 이후 선택 프레임에 재사용한다. 선택 프레임은 초기화나 추론에 오래 걸려도 결과가 준비될 때까지 기다린다.

## 설정

```yaml
YoloDetect:
  classes: null
  confidence: 0.25
  gpu_id: 0
  inference_interval: 1
```

- `classes`: 음수가 아닌 정수 클래스 번호 목록. 기본값 `null`은 전체 클래스이다.
- `confidence`: 0보다 크고 1 이하인 신뢰도. 기본값은 0.25이다.
- `gpu_id`: 음수가 아닌 GPU 번호. 기본값은 0이다.
- `inference_interval`: 1 이상의 정수. 기본값은 1이며 첫 입력부터 지정 간격으로 선택한다. 간격 3은 1·4·7번째 입력을 추론한다.

간격으로 건너뛴 입력은 `detections=None`으로 전달한다. 단일 `YoloDetect`는 모델 동명 `.yml`을 읽지 않으며 `timeout`도 적용하지 않는다. `YoloDetectBatch`의 배치 수집 설정은 별도 계약이다.

## 선택적 비동기 실행

```python
from pipeworks.embedded import Async, YoloDetect

pipeline.step(Async(YoloDetect(model_path), timeout_ms=5))
```

```yaml
Async:
  timeout_ms: 5
  step:
    classes: [2]
    confidence: 0.4
    gpu_id: 0
    inference_interval: 1
```

공통 `Async`가 작업용 입력을 복사하고 제한 시간·오류·사용 중 원본 통과와 늦은 결과 폐기를 담당한다. 모델 실행 자체는 동기 방식이지만 공통 작업 스레드에서 호출된다. 실행 중 추론을 강제로 취소하지 않는다.

원본 통과는 기존 속성을 그대로 보존한다. 원래 `detections`가 없던 입력은 시간 초과 후에도 이 속성이 없을 수 있다. 사용 중 통과한 입력은 감싼 모델 단계가 보지 않으므로 모델의 간격 카운터는 실제 제출된 입력을 기준으로 증가한다.

## 결과와 통계

```python
result = getattr(context, "detections", None)
if result is not None:
    boxes = result.boxes.xyxy
    confidence = result.boxes.conf
    classes = result.boxes.cls
```

`context.detections`는 Ultralytics 결과 객체이다. 원본 프레임은 그대로 유지한다. `StreamReport`에는 실제 예측 실행부터 GPU 완료까지의 시간을 기록한다. 실패한 예측도 기록하되 입력 검증이나 모델 초기화 실패는 추론 건수에 포함하지 않는다. 개별 컨텍스트에 별도 추론 시간 필드를 추가하지 않는다.

## 오류 처리

지원하지 않는 형식, 홀수·0 해상도, 잘못된 자료형·프레임 크기, GPU 번호 불일치는 예외이다. 직접 사용할 때 예외는 처리 반복자를 끝낸다. 지연·오류가 있어도 영상을 통과시키려면 공통 `Async`를 조합한다.

## 관련 문서

- [Async](async.md): 공통 비동기 실행과 원본 통과 정책.
- [YoloDetectBatch](yolo_detect_batch.md): 공유 배치 감지.
- [TensorRTInference](tensor_rt_inference.md): 원시 GPU 텐서 추론.
- [파이프라인](../pipeline.md): 단계 조립과 구성.
