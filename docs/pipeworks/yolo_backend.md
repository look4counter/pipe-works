# yolo_backend: 사용자 GPU 실행부 확장

구현: src/pipeworks/yolo_backend.py. 일반 앱은 [YoloInference](embedded/yolo_inference.md)를 사용하고, 새 모델 실행 방식을 연결할 때 모듈:클래스 문자열로 backend를 지정합니다. YoloBackend Protocol은 infer(inputs) 계약을 표현하며 반드시 상속할 필요는 없습니다.

## 사용자 클래스

생성자는 model_path와 gpu_id 두 인자를 받고 infer(inputs)를 제공합니다. 모듈 경로는 점으로 연결한 Python 식별자, 클래스명은 단일 식별자여야 합니다. 중첩 속성 경로나 함수 팩터리 경로는 지원하지 않습니다.

```python
# 앱의 my_backends.py
import torch


class MyBackend:
    def __init__(self, model_path, gpu_id):
        self.model = torch.jit.load(
            str(model_path), map_location=torch.device("cuda", gpu_id)
        ).eval()

    def infer(self, inputs):
        if isinstance(inputs, dict):
            return self.model(**inputs)
        return self.model(inputs)
```

```python
from pathlib import Path
from pipeworks.embedded import YoloInference

step = YoloInference(
    Path("models/model.pt").resolve(),
    backend="my_backends:MyBackend",
    gpu_id=0,
)
```

새 실행부 모듈을 중앙 프로세스도 가져올 수 있어야 합니다. pipeworks의 enum·소스는 수정하지 않습니다. 전처리·후처리와 NMS는 이 계약에 자동 포함되지 않습니다.

## 입력과 출력

입력은 지정 GPU의 일반 strided 텐서 또는 비어 있지 않은 이름별 텐서 사전입니다. 각 텐서는 1차원 이상이고 모든 축이 양수여야 합니다. 사전 키는 공백뿐이지 않은 문자열입니다. 공유 배치 입력은 첫 축이 1이어야 합니다. 입력 이름·형상·자료형은 모델이 결정하며 추론 전에 GPU에서 contiguous로 맞춥니다.

출력은 GPU 텐서 또는 비어 있지 않은 텐서 사전·목록·튜플의 중첩 구조입니다. normalize_outputs가 단일 텐서를 output0, 목록을 output0·output1, 중첩 경로를 /로 연결해 평탄화합니다. 사전 이름은 보존합니다. 이름 충돌·비텐서·빈 컨테이너·CPU 또는 다른 GPU 출력은 오류입니다. 각 텐서를 복제해 다음 모델 호출의 버퍼 재사용으로 이전 결과가 바뀌지 않게 합니다. 개별 실행은 스칼라·빈 출력 텐서도 허용하지만 공유 배치는 모든 출력의 첫 축이 요청 수와 같아야 합니다.

infer는 호출자가 지정한 현재 CUDA 스트림에서 실행됩니다. 실행부가 별도 스트림을 사용한다면 현재 스트림의 준비 순서와 결과 완료 순서를 직접 연결해야 합니다. 일반 실행은 no_grad와 GpuOnly 감시 아래 실행하고 완료 후 결과를 전달합니다. 네이티브 라이브러리 내부 연산은 PyTorch 감시가 포착하지 못하므로 실행부도 동일한 GPU 계약을 지켜야 합니다.

## GPU 전용 제약

GpuOnly는 CPU·다른 GPU 텐서 연산과 장치 전환, GPU 값의 CPU scalar 읽기를 거부합니다. 입력 데이터에 대한 item·bool·equal·allclose 같은 CPU 값 판정은 사용할 수 없습니다. 파일 로딩·정적 메타데이터는 CPU에서 처리할 수 있고 TorchScript 스칼라 상수 등 알려진 불변 메타데이터는 예외로 처리합니다. CPU 출력으로 자동 대체하거나 CPU 출력을 GPU로 자동 이동하지 않습니다.

## 모듈 도우미 목록

| 이름 | 역할 |
| --- | --- |
| validate_backend / load_backend | 문자열 검증, CUDA·모델 파일 확인, 생성자 호출, infer 존재 확인 |
| validate_gpu / validate_inputs | 장치·입력 컨테이너·형상·배치 축 검증 |
| validate_module_gpu | 모델 parameter·buffer 장치 확인 |
| input_signature | 자료형·이름·비배치 형상으로 호환 키 생성 |
| contiguous_inputs / concatenate_inputs | 연속 입력 생성, 배치 첫 축 결합 |
| normalize_outputs | GPU 출력 검증·이름 평탄화·복제 |
| batch_settings | 모델 옆 .yml의 max_batch_size와 timeout_ms 읽기. 반환 시간은 초 |
| GpuOnly | PyTorch 연산의 GPU 전용 계약 감시 |

도우미는 내부 추론 경로에서도 사용합니다. 직접 조합하면 동기화·오류 전달·자원 수명을 호출자가 책임져야 합니다. 모델 실행은 YoloInference 또는 [공유 infer](local_yolo_inference.md)를 통해 사용하는 것이 기본 경로입니다. [실행부별 차이](yolo_backends/README.md)를 참고하세요.
