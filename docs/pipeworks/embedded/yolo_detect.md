# YoloDetect: 개별·배치 GPU YOLO 객체 감지

공유 배치 경로는 작업자 최초 준비 시 모델 경로를 정규화하고 존재를 검사한다. 같은 입력 경로로 기존 작업자를 재사용할 때는 resolve/is_file을 호출하지 않는다. 이미 로드된 모델은 파일 삭제 후에도 추론하며 파일·캐시된 심볼릭 링크 변경으로 자동 교체하지 않는다. 새로운 모델 로드에는 실제 파일이 필요하다. 상대경로는 호출 작업 디렉터리로 구분한다. 개별 모드의 기존 로드 방식은 유지한다.

선택 프레임의 모델 로드·변환·추론·좌표 복원을 호출 스레드에서 동기로 실행한다. 입력 준비 이벤트를 기다리는 별도 CUDA 추론 스트림을 사용하며, GPU 결과가 준비된 다음에 같은 입력 컨텍스트를 전달한다. 내부 Python 작업자나 시간 제한은 없으며, 잘못된 입력·모델 로드·추론 오류는 호출자에게 예외로 전파한다.

입력은 설정된 GPU의 uint8 NV12 프레임이다. 영상과 감지 텐서를 CPU로 복사하지 않는다. 결과의 `orig_img`는 원본 해상도의 GPU RGB float HWC 텐서이며, `boxes.data`는 원본 좌표의 GPU 텐서이다. 빈 박스 결과도 정상이다.

## 사용법

```python
from pathlib import Path
from pipeworks.embedded import YoloDetect

pipeline.step(YoloDetect(Path("models/yolo11n.pt")))
pipeline.step(YoloDetect(Path("models/yolo11n.pt"), batch=True))
```

`.pt`와 Ultralytics에서 지원하는 `.engine` 모델 경로를 사용할 수 있다. 모델은 입력 스트림의 첫 선택 프레임에서 준비하고 이후 선택 프레임에 재사용한다. 선택 프레임은 초기화나 추론에 오래 걸려도 결과가 준비될 때까지 기다린다.

## 설정

```yaml
YoloDetect:
  classes: null
  confidence: 0.25
  gpu_id: 0
  inference_interval_frame: 1
```

- `classes`: 음수가 아닌 정수 클래스 번호 목록. 기본값 `null`은 전체 클래스이다.
- `confidence`: 0보다 크고 1 이하인 신뢰도. 기본값은 0.25이다.
- `gpu_id`: 음수가 아닌 GPU 번호. 기본값은 0이다.
- `inference_interval_frame`: 1 이상의 정수. 기본값은 1이며 첫 입력부터 지정 간격으로 선택한다. 간격 3은 1·4·7번째 입력을 추론한다.

기존 `inference_interval` 설정은 `inference_interval_frame`으로 변경해야 한다. 값과 프레임 단위 동작은 동일하며 이전 키는 변경 안내 오류로 처리한다.

간격으로 건너뛴 입력은 `detections=None`으로 전달한다. `batch`는 생성자의 불리언 인자이며 기본값은 `False`이다. YAML에서 실행 모드를 바꾸지는 않는다.

## 선택적 배치 처리

`batch=False`는 위의 기본 동기 경로를 유지하며 모델 동명 `.yml`을 읽지 않는다. `batch=True`는 `YoloDetect`에서 독립 GPU RGB 텐서를 생성하고 원본 영상 사용 종료 이벤트와 함께 `local_yolo.infer()`에 직접 제출한다. NV12 보호 복제는 하지 않는다. 같은 모델 경로의 여러 요청을 작업자에서 모아 추론하며 한 영상의 다음 프레임을 미리 읽지 않는다. local_yolo 직접 호출의 기존 NV12 입력도 지원한다.

모델 옆 `yolo11n.yml`에는 다음 배치 수집 설정을 둔다.

```yaml
max_batch_size: 8
timeout_ms: 20  # 배치를 모으는 최대 시간, 밀리초
```

기존 모델 YAML의 `timeout`은 값의 밀리초 단위를 유지해 `timeout_ms`로 변경해야 한다. 이전 키는 변경 안내 오류로 거부한다.

이 `timeout_ms`은 추론 대기 제한이 아니다. 실제 묶음 크기는 동시에 들어오는 요청 수·동일 추론 옵션·모델 엔진의 배치 지원 범위에 따라 달라진다. 실행 중 classes·confidence·gpu_id·inference_interval_frame 설정 변경은 배치 경로에도 입력 경계에서 전달한다.

배치 경로는 기존 동작처럼 실패를 기록하고 `detections=None`으로 원본을 전달한다. 개별 경로의 오류는 예외로 전파한다.

## 선택적 비동기 실행

```python
from pipeworks.embedded import CudaAsync, YoloDetect

pipeline.step(CudaAsync(YoloDetect(model_path), timeout_ms=5))
# 배치 처리와 시간 제한을 함께 사용
pipeline.step(CudaAsync(YoloDetect(model_path, batch=True), timeout_ms=5))
```

```yaml
CudaAsync:
  timeout_ms: 5
YoloDetect:
  classes: [2]
  confidence: 0.4
  gpu_id: 0
  inference_interval_frame: 1
```

공통 `CudaAsync`가 제한 시간·오류·사용 중 원본 통과와 늦은 결과 폐기를 담당한다. 모든 경로에서 보호 복사를 하지 않는다. 실행 중 추론을 강제로 취소하지 않는다.

개별·배치 모드 모두 NV12→RGB 생성 직후 `release_frame(ready_event=...)`으로 원본 영상 사용 종료를 알린다. 타임아웃 시 이벤트 완료가 확인되면 원본을 그대로 전달하며, 아직 전처리 중이거나 이벤트가 미완료면 해당 프레임을 폐기한다. 신호 이후 같은 CudaAsync의 후속 Step은 원본을 사용하지 않아야 한다. RGB 텐서와 배치 텐서 생성에 필요한 할당은 유지한다.

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

지원하지 않는 형식, 홀수·0 해상도, 잘못된 자료형·프레임 크기, GPU 번호 불일치는 예외이다. 직접 사용할 때 예외는 처리 반복자를 끝낸다. 지연·오류가 있어도 영상을 통과시키려면 공통 `CudaAsync`를 조합한다.

## 관련 문서

- [CudaAsync](async.md): 공통 비동기 실행과 원본 통과 정책.
- [TensorRTInference](tensor_rt_inference.md): 원시 GPU 텐서 추론.
- [파이프라인](../pipeline.md): 단계 조립과 구성.
