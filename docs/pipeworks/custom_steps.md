# 사용자 Step 작성과 배포

사용자 코드는 앱의 원하는 패키지에 둡니다. pipeworks 내부에 파일을 추가하지 않아도 [Step](models.md)을 상속하고 Pipeline.step에 등록할 수 있습니다. configure와 process를 모두 구현해야 하며 설정이 없어도 빈 configure가 필요합니다.

## 최소 구현과 기본값 복원

```python
from pipeworks.models import Step


class Scale(Step):
    def __init__(self, *, factor=2):
        self._set_config_defaults(factor=factor)

    def configure(self, config):
        value = self._resolve_config(config).factor
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError("factor는 숫자여야 합니다.")
        self.factor = value

    def process(self, inputs):
        for item in inputs:
            item.scaled = item.value * self.factor
            yield item
```

_set_config_defaults는 최초 값을 깊게 복사하고 configure를 즉시 호출합니다. configure가 사용할 상태를 먼저 초기화해야 합니다. _resolve_config는 최초 기본값과 전달된 SimpleNamespace를 합칩니다. YAML 섹션은 Scale입니다. 설정 검증을 끝낸 뒤 속성을 갱신하면 잘못된 값으로 일부 상태만 바뀌는 일을 줄일 수 있습니다.

## 입력·출력과 자원 수명

process는 반복자를 받고 반복자를 반환합니다. 일반 처리 단계는 입력 하나를 받아 같은 컨텍스트나 새 PipelineContext를 출력합니다. Source는 상류 입력 없이 자체 컨텍스트를 만들고 Sink는 입력을 소비한 뒤 출력하지 않을 수 있습니다. CudaAsync와 EveryNFrames의 내부 단계는 입력 하나당 출력 하나 계약이므로 일반 Source·출력 없는 Sink·다중 입력 집계 단계를 넣을 수 없습니다.

PipelineContext의 필드는 동적입니다. 필수 입력을 명시하고 누락 시 오류를 내거나 선택 입력은 getattr로 확인합니다. 임의 사용자 필드가 디코더·인코더의 새 컨텍스트로 자동 승계되지는 않습니다. 인코딩 전에 필요한 감지 결과를 소비하세요.

열린 파일·네트워크·모델·CUDA 자원은 process 안에서 지연 생성하고 try/finally에서 정리합니다. 상류를 조기 종료하는 단계는 자신이 소유한 반복자도 닫아야 합니다. 배치 중앙 실행을 사용할 때 생성자에 열린 자원을 보관하면 직렬화에 실패할 수 있습니다.

## CUDA와 비동기 공유

NvidiaDecode가 제공하는 cuda_stream에서 frame 연산을 실행합니다. 다른 스트림으로 넘기면 CUDA 이벤트로 준비·완료 순서를 직접 보장합니다. CudaAsync와 TapSkipIfBusy는 프레임·텐서를 깊게 복사하지 않습니다. 공유 입력은 읽기 전용으로 사용하고 결과는 독립 데이터로 만듭니다. Overlay처럼 원본을 수정하는 처리는 비동기 추론 묶음 뒤에 둡니다.

독립 RGB 텐서를 만든 뒤 원본 프레임 읽기가 끝나는 이벤트로 [release_frame](execution.md)을 호출할 수 있습니다. 이 약속 이후 같은 CudaAsync 묶음의 모든 단계가 원본을 다시 사용하지 않아야 합니다. CPU 호출이 반환됐다는 이유만으로 GPU 읽기가 끝났다고 판단하면 안 됩니다.

## 코드 재로드와 오류

Pipeline은 일반 사용자 Step을 Hotswap으로 감쌉니다. 파일에 정의된 클래스는 처리 경계에서 코드 변경을 감지하고 속성 사전을 얕게 보존해 새 구현에 넘깁니다. 기존 생성기 지역 상태는 재시작되고 생성자만의 초기화에 의존하면 새 구현과 맞지 않을 수 있습니다. 가져온 공통 라이브러리까지 자동 재로드하지 않습니다.

일반 Hotswap의 기본 recover_errors=True는 내부 실행 오류 시 아직 출력하지 않은 원본 입력을 전달하고 재시도할 수 있습니다. 중첩 객체·GPU 메모리 제자리 변경은 되돌리지 않습니다. 실패를 호출자에게 전파하려면 Hotswap(my_step, recover_errors=False)를 명시합니다. CudaAsync·EveryNFrames 내부 사용자 단계는 자체 계약에 따라 recover_errors=False로 감쌉니다. 자세한 복구 범위는 [Hotswap](hotswap.md)을 확인하세요.

## 앱 배포

사용자 Step·의존 도우미·설정·모델 파일을 앱과 함께 둡니다. 중앙 실행에서 문자열로 가져오는 사용자 backend와 동적 import 모듈은 동일 Python 환경 또는 PYTHONPATH에서 import 가능해야 합니다. 앱 진입점은 if __name__ == "__main__"으로 보호합니다. [독립 앱 예제](getting_started.md)를 그대로 출발점으로 사용할 수 있습니다.
