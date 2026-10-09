# CudaAsync: 대기를 제한하는 공통 비동기 단계

CudaAsync는 다른 Step을 별도 작업 스레드에서 실행한다. 기한 안에 완료하면 결과를 같은 원본 컨텍스트에 적용한다. 기본 제한 시간은 5ms이며 입력 보호 복사는 하지 않는다.

```python
from pipeworks.embedded import CudaAsync, YoloDetect

pipeline.step(CudaAsync(YoloDetect(model_path), timeout_ms=10))
pipeline.step(CudaAsync(YoloDetect(model_path, batch=True), timeout_ms=10))
```

직접 가져오기는 `from pipeworks.embedded.cuda_async import CudaAsync`를 사용한다. 일반 사용자 Step도 감쌀 수 있다.

## 전달 규칙

- 정상 완료하면 결과 속성을 원본에 반영한다.
- 이미 다른 요청이 진행 중이면 새 입력을 제출하지 않고 그대로 전달한다. 요청을 쌓지 않는다.
- 타임아웃 시 원본 사용 종료가 확인되거나 요청 전체가 GPU 정리까지 끝났으면 원본을 그대로 전달한다.
- 아직 원본을 사용 중이거나 종료 신호가 없으면 해당 프레임만 폐기한다. 복사하거나 작업 완료를 기다리지 않는다.
- 이미 실행 중인 함수·GPU 작업을 강제로 중단하지 않는다. 늦은 결과는 폐기한다.
- 정리된 처리 오류는 로그를 남기고 원본을 전달하며 다음 요청에서 처리 반복자를 재생성한다.
- 입력 종료는 실행 중인 작업을 무한히 기다리지 않는다. 작업자가 끝난 후 자원을 정리한다.
- 인스턴스당 진행 중 요청은 하나이며 이전 실행이 정리를 마칠 때까지 재사용 요청은 통과한다.

## 원본 영상 사용 종료

```python
from pipeworks.execution import release_frame

rgb = convert_nv12_to_rgb(frame)
frame_done = torch.cuda.Event()
frame_done.record(torch.cuda.current_stream())
release_frame(ready_event=frame_done)
# 이후에는 rgb와 그로부터 만든 model_input만 사용한다.
```

영상 전처리는 원본과 메모리를 공유하지 않는 RGB 텐서를 만든 다음 원본을 읽는 모든 GPU 작업 뒤에 이벤트를 기록한다. CudaAsync는 타임아웃 시 query로 완료 여부만 확인한다. 완료를 기다리지 않으며 조회 실패 시 프레임을 폐기한다.

release_frame은 단일·복수 Step에서 적용한다. 호출 이후 같은 CudaAsync 안의 후속 Step은 원본을 다시 읽거나 수정하지 않아야 한다. 원본을 그리는 BoxOverlay는 바깥에 둔다. model_input과 model_output 같은 독립 텐서는 계속 사용할 수 있다. 다른 공유 데이터도 읽기 전용이다. 이벤트 없이 호출하는 것은 원본 읽기가 이미 완료됐다는 약속이며, CUDA 작업이 아직 남아 있으면 이벤트를 제공해야 한다.

기존 release_input은 모든 공유 입력의 사용 종료를 뜻하고 단일 Step에서만 적용한다. 영상 종료와 다른 계약이다. 두 신호 모두 요청별로 격리되며 CudaAsync 밖에서는 아무 동작도 하지 않는다.

YOLO 개별·배치 및 예제 TensorRTPreProcess는 RGB 생성 이후 release_frame을 호출한다. 별도 신호를 보내지 않는 일반 Step도 사용할 수 있지만 실행 중 타임아웃된 프레임은 폐기된다.

## 여러 Step과 설정

```python
CudaAsync(
    TensorRTPreProcess(),
    TensorRTInference(model_path, batch=True),
    TensorRTPostProcess(),
    timeout_ms=20,
)
```

하나 이상의 Step을 위치 인자로 나열하며 전체 요청에 하나의 기한을 적용한다. 만료 이후 미시작 단계는 건너뛴다. 단계별 반복자 상태는 유지하며 오류 시 연결 전체를 정리한다. 소스·다중 입력 집계·다중 출력 단계는 지원하지 않는다.

```yaml
CudaAsync:
  timeout_ms: 20
YoloDetect:
  classes: [2]
  inference_interval_frame: 1
TensorRTInference:
  gpu_id: 0
```

timeout_ms는 유한한 0 이상의 숫자다. 0이면 결과를 기다리지 않는다. CudaAsync 구성은 timeout_ms만 받으며 내부 Step은 각 클래스명 최상위 YAML 섹션에서 설정받는다. 사용자·내장·중첩 Step의 설정은 독립 적용하고 잘못된 변경은 해당 단계의 이전 설정을 유지한다. 사용자 Step의 코드 핫스왑은 기본 0.5초 간격으로 처리 경계에서 확인한다.

## 입력 수명과 CUDA 스트림

작업 컨텍스트의 속성 사전만 분리한다. 텐서·프레임·중첩 객체는 공유하며 읽기 전용이다. 결과는 새 속성이나 새 데이터로 반환한다. 원본 참조는 실행 중 작업이 끝날 때까지 유지한다. DLPack 공급자는 텐서가 살아 있는 동안 버퍼를 해제하거나 재사용하지 않아야 한다.

CudaAsync는 장치별 모델 스트림을 생성·재사용하며 원본 input.cuda_stream은 영상·인코딩용으로 유지한다. 내부 연산은 현재 CUDA 스트림을 사용하고 필요하면 current_model_stream()으로 조회한다. YOLO·TensorRT의 공유 배치 작업자는 자체 스트림을 유지한다.

CudaAsync의 보호 복사 제거는 RGB 변환·리사이즈·모델 입출력·배치 stack에 필요한 GPU 메모리 할당까지 제거하는 것은 아니다. 시간 초과는 외부 부작용을 취소하지 않는다. CUDA 런타임 호출 자체의 지연에는 절대 시간 상한을 보장하지 않는다.
