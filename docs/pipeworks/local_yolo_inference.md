# local_yolo_inference: 프로세스 안의 공유 GPU 배치

구현: src/pipeworks/local_yolo_inference.py. 일반 Pipeline 사용자는 YoloInference(batch=True)를 선택합니다. 이 모듈의 infer는 현재 프로세스의 모델 작업자에 직접 요청하며 자체적으로 중앙 프로세스를 시작하지 않습니다. 이름의 local이 CPU 추론을 뜻하지는 않습니다.

## 직접 호출 API

```text
infer(
    model_path, inputs, gpu_id=0, *, backend="torchscript",
    profile_index=0, ready_event=None,
    on_inference_complete=None, on_profile_complete=None,
)
```

| 인자 | 계약 |
| --- | --- |
| model_path | 실제 모델 파일 경로. 앱 기준 절대경로 권장 |
| inputs | 지정 GPU의 텐서 또는 이름별 사전. 모든 입력 첫 축은 1 |
| gpu_id | bool을 제외한 음수가 아닌 정수 |
| backend | torchscript·ultralytics·tensorrt 또는 모듈:클래스. 직접 호출 기본은 torchscript |
| profile_index | TensorRT 최적화 프로파일. 다른 실행부는 0만 허용 |
| ready_event | 입력 생산 완료 CUDA 이벤트. 생략하면 호출자의 현재 GPU 스트림에서 기록 |
| on_inference_complete | 성공 시 소요 시간(초)을 인자로 호출 |
| on_profile_complete | 요청별 Profile을 인자로 호출. 요청 오류 검사 전에 호출될 수 있음 |

요청 완료까지 동기 대기하고 이름별 GPU 출력 사전을 반환합니다. 자체 시간 제한·취소 인자는 없습니다. 작업자 오류는 문자열을 포함한 RuntimeError로 전달하며 입력·설정 검증은 ValueError 등으로 직접 실패할 수 있습니다. 입력 텐서는 대기 중 수정하거나 재사용하지 않습니다.

```python
from pathlib import Path
import torch
from pipeworks import Backend
from pipeworks.local_yolo_inference import infer


def run_prepared_model(model_path, prepared_input, producer_stream):
    ready = torch.cuda.Event()
    ready.record(producer_stream)
    return infer(
        Path(model_path).resolve(), prepared_input,
        gpu_id=producer_stream.device.index,
        backend=Backend.TORCHSCRIPT,
        ready_event=ready,
    )
```

prepared_input의 형상·자료형은 모델에 맞춰 사용자가 준비합니다. [설정 파일](configuration.md)의 모델 YAML 규칙을 따릅니다.

## 공유 조건과 수명

모델 경로와 backend별로 작업자를 캐시합니다. 한 작업자는 GPU·프로파일·입력 이름·자료형·비배치 형상이 같은 요청만 묶으며 세션은 GPU·프로파일별, 스트림은 GPU별로 유지합니다. ID는 공유 조건에 포함되지 않습니다. 입력을 첫 축으로 결합하고 출력의 첫 축이 요청 수와 같은지 검증한 뒤 요청별 배치 1 GPU 사본을 반환합니다.

배치 수집 기한은 가장 오래된 요청 도착 시점부터 계산하므로 이미 큐에서 오래 기다렸다면 추가 대기 시간이 줄어듭니다. 모델 YAML은 작업자 최초 생성 때 읽고 파일 변경으로 자동 재생성하지 않습니다. 모델·경로 별칭 캐시와 작업자에는 공개 종료·삭제 API가 없습니다. 교체가 필요하면 해당 실행 프로세스를 재시작합니다.

실행 실패 시 해당 GPU·프로파일 세션을 제거하고 배치의 모든 요청을 깨워 오류를 전달합니다. 다음 요청에서 모델을 다시 준비합니다. 실행이 끝나면 요청의 입력·이벤트 참조와 임시 배치 텐서를 정리합니다. 콜백은 호출자 문맥에서 호출합니다.

[배치 수집기](batch_collector.md), [경로 캐시](model_worker.md), [중앙 실행](main.md)을 참고하세요.
