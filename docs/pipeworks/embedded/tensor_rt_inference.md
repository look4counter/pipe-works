# TensorRTInference: GPU 추론 전용 단계

`TensorRTInference`는 전처리 단계가 만든 `context.model_input`의 GPU 텐서를 TensorRT 엔진으로 추론하고 원시 출력을 `context.model_output`에 넣습니다. 리사이즈·색 변환·정규화·자료형 변환·NMS·좌표 복원은 수행하지 않습니다.

## 파이프라인 연결

```python
from pathlib import Path
from pipeworks.embedded import TensorRTInference

pipeline.step(preprocess_step)
pipeline.step(TensorRTInference(Path("models/model.engine")))
pipeline.step(postprocess_step)
```

입력이 하나인 엔진에는 `context.model_input`에 GPU 텐서를 직접 넣습니다. 입력 이름은 엔진에서 자동으로 읽습니다. 입력이 여러 개인 엔진에는 `{실제 입력 이름: GPU 텐서}` 사전을 넣어 모든 입력을 제공해야 합니다.

출력은 하나여도 항상 `{실제 출력 이름: GPU 텐서}` 사전입니다. 후처리 단계에서 필요한 출력을 선택합니다. 입력과 출력 이름·자료형·형상은 엔진에서 읽으며 코드에 고정하지 않습니다. 자료형과 입력 크기는 전처리 단계가 엔진 요구에 맞춰야 합니다. 비연속 입력은 값과 형상을 유지한 GPU 연속 복제만 수행합니다.

```python
if context.model_output is not None:
    for name, tensor in context.model_output.items():
        # tensor는 원시 GPU 출력이며 후처리 단계에서 해석합니다.
        consume(name, tensor)
```

## 설정

파이프라인 YAML의 클래스명 섹션에 GPU 번호와 추론 대상 선택 간격을 설정합니다.

```yaml
TensorRTInference:
  gpu_id: 0
  inference_interval: 1
```

`models/model.engine`의 동명 `models/model.yml`에는 선택적인 외부 플러그인 라이브러리를 설정합니다.

```yaml
plugins: [] # 예: [custom.dll] 또는 [libcustom.so]
```

기존 `timeout`은 읽지 않으며 자체 시간 제한은 없습니다. `plugins`의 상대 경로는 모델 YAML 디렉터리 기준입니다. 설정은 실행 시작에 읽습니다. 배치 차원은 입력 텐서가 결정하며 별도 요청을 모으지 않습니다. 클래스·신뢰도 필터는 후처리 단계의 책임입니다.

## 동기 실행과 자원 수명

호출 스레드에서 입력 생산 완료를 확인하고 별도 CUDA 스트림에서 엔진을 실행합니다. 연속 GPU 입력은 복제하지 않으며 비연속 입력만 연속화합니다. 전처리는 `context.cuda_stream`에서 입력을 준비하거나 준비 완료를 보장해야 합니다.

GPU 완료 후 결과를 전달하며 간격으로 건너뛴 입력은 `model_output=None`입니다. 입력과 영상은 보존하고 오류는 호출자에 전파합니다. 시간 제한·오류 통과가 필요하면 전처리·추론·후처리를 공통 `CudaAsync(..., timeout_ms=20)`로 감쌉니다. 이미 실행 중인 GPU 작업은 강제 취소하지 않습니다.

## 엔진과 플러그인

TensorRT 표준 플러그인을 초기화하고 엔진에 직렬화된 플러그인·실행 코드 로딩을 허용합니다. 외부 공유 라이브러리는 Runtime 플러그인 레지스트리에서 엔진 역직렬화 전에 로드합니다. 라이브러리는 TensorRT 레지스트리 로딩 방식에 맞춰 내보낸 플러그인이어야 합니다. 엔진에 플러그인 정보만 있고 구현이 내장되어 있지 않으면 필요한 외부 라이브러리를 지정해야 합니다.

일반 TensorRT 엔진과 Ultralytics JSON 메타데이터 헤더가 앞에 붙은 엔진을 읽습니다. 엔진을 생성하거나 변환하지 않습니다. 입력에 따른 동적 크기와 데이터 의존 출력 할당을 지원하며 최적화 프로파일 0을 사용합니다.

GPU 위치의 LINEAR 바인딩만 지원합니다. CPU 형상 바인딩, 벡터화 저장 포맷, 4비트 자료형 등 지원하지 않는 형식은 예외로 알립니다. TensorRT와 엔진·플러그인 버전 및 GPU 호환성은 실행 환경에서 맞춰야 합니다.

## 검증

`tests/test_tensor_rt_inference.py`는 모의 TensorRT API와 실제 CUDA 텐서로 GPU 값·이름·자료형·동적 출력·플러그인 로딩·동기 실행·무복제 입력과 CudaAsync 조합을 확인합니다. 실제 TensorRT 엔진 생성·실행 및 예제 YOLO plan 검증도 통과했습니다.
## 선택적 공유 배치

`TensorRTInference(model_path, batch=True)`는 local_tensor_rt에 요청한다. 기본 batch=False는 기존 동기 개별 경로다. 전처리는 프레임마다 배치 1 텐서를 만들면 된다. 공유 실행기가 여러 입력을 모아 추론하고 각 요청에 배치 1 GPU 출력 사전을 반환한다.

모델 YAML의 max_batch_size와 밀리초 timeout은 배치 크기와 수집 기한이다. 배치 엔진은 수집 가능한 모든 크기를 지원해야 하며 입력·출력의 첫 축이 배치여야 한다. 고정 배치 1 엔진에는 max_batch_size=1을 사용한다. plugins 설정도 유지한다. 배치 모드도 자체 추론 제한은 없으며 오류는 호출자에 전파한다. 시간 제한·영상 통과는 CudaAsync가 담당한다.
## 원본 영상 사용 종료와 비동기 조합

예제 TensorRTPostProcess는 원시 model_output을 NMS에 직접 전달한다. NMS의 좌표 제자리 변환을 허용하며 원시 출력을 보존하는 clone은 하지 않는다. 후처리 이후에는 input.detections만 사용하고 model_output은 정리한다. BoxOverlay는 detections를 읽어 frame에 표시하므로 원시 출력 복제를 요구하지 않는다.

예제 TensorRTPreProcess는 독립 RGB 생성 직후 원본 읽기의 CUDA 완료 이벤트를 기록해 release_frame을 호출한다. 단일·복수 CudaAsync에서 신호를 적용한다. 이후 추론·후처리는 독립 model_input·model_output만 사용하고 원본을 다시 읽지 않는다. BoxOverlay는 CudaAsync 바깥에 둔다.

CudaAsync는 보호 복사를 하지 않는다. 타임아웃 시 원본 사용 완료가 확인되면 원본을 전달하고, 아직 사용 중이거나 신호가 없으면 해당 프레임을 폐기한다. 사용자 전처리도 동일한 신호 계약을 사용해야 한다. TensorRTInference가 임의 입력 텐서의 원본 별칭 여부를 판단해 자동으로 해제하지는 않는다.
