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

`models/model.engine`의 동명 `models/model.yml`에는 결과 대기 제한과 선택적인 외부 플러그인 라이브러리를 설정합니다.

```yaml
timeout: 5  # 밀리초, 파일·항목 부재 시에도 기본 5
plugins: [] # 예: [custom.dll] 또는 [libcustom.so]
```

`timeout`은 요청 제출부터 결과 준비까지 기다리는 최대 시간입니다. 유한한 0 이상 숫자만 허용하며 0이면 기다리지 않습니다. `plugins`의 상대 경로는 모델 YAML 디렉터리 기준입니다. 설정은 실행 시작에 읽습니다. 배치 차원은 입력 텐서가 결정하며 `max_batch_size`로 별도 요청을 모으지 않습니다. 클래스·신뢰도 필터는 후처리 단계의 책임입니다.

## 비동기와 자원 수명

작업자 전용 CUDA 스트림에서 엔진 로드·추론을 수행합니다. 생산자 `context.cuda_stream`이 있으면 그 스트림에서 입력을 GPU 복제하고, 없으면 해당 GPU의 현재 스트림을 사용합니다. 전처리는 이 스트림에서 입력을 준비하거나 준비 완료를 보장해야 합니다.

제한 시간 안에 준비된 결과만 해당 컨텍스트에 연결합니다. 시간 초과·실패·추론 간격·작업자 사용 중인 프레임은 `model_output=None`으로 전달합니다. 늦은 결과를 다른 프레임에 적용하거나 이미 전달한 컨텍스트를 수정하지 않습니다. 작업자와 실행 중 요청은 단계 인스턴스당 최대 1개이며 종료와 반복자 닫기는 멈춘 추론을 기다리지 않습니다. 입력 영상과 `model_input`은 보존합니다.

## 엔진과 플러그인

TensorRT 표준 플러그인을 초기화하고 엔진에 직렬화된 플러그인·실행 코드 로딩을 허용합니다. 외부 공유 라이브러리는 Runtime 플러그인 레지스트리에서 엔진 역직렬화 전에 로드합니다. 라이브러리는 TensorRT 레지스트리 로딩 방식에 맞춰 내보낸 플러그인이어야 합니다. 엔진에 플러그인 정보만 있고 구현이 내장되어 있지 않으면 필요한 외부 라이브러리를 지정해야 합니다.

일반 TensorRT 엔진과 Ultralytics JSON 메타데이터 헤더가 앞에 붙은 엔진을 읽습니다. 엔진을 생성하거나 변환하지 않습니다. 입력에 따른 동적 크기와 데이터 의존 출력 할당을 지원하며 최적화 프로파일 0을 사용합니다.

GPU 위치의 LINEAR 바인딩만 지원합니다. CPU 형상 바인딩, 벡터화 저장 포맷, 4비트 자료형 등 지원하지 않는 형식은 오류 로그와 함께 결과 없이 전달합니다. TensorRT와 엔진·플러그인 버전 및 GPU 호환성은 실행 환경에서 맞춰야 합니다.

## 검증

`tests/test_tensor_rt_inference.py`는 모의 TensorRT API와 실제 CUDA 텐서로 GPU 값·이름·자료형·동적 출력·플러그인 로딩·비동기 수명을 확인합니다. 실제 TensorRT가 설치된 환경에서는 작은 엔진을 생성해 직접 실행하는 검증도 수행합니다. 현재 환경에서는 TensorRT가 없어 이 실제 실행 검증을 건너뛰었습니다.
