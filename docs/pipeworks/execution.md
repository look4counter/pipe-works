# execution: 비동기 입력 수명과 소스 취소

구현: src/pipeworks/execution.py. 사용자 GPU 전처리는 release_frame을 사용할 수 있습니다. 이 함수들은 메모리를 직접 해제하는 명령이 아니라 현재 CudaAsync 요청에 보내는 수명 약속입니다.

| 함수 | 계약 |
| --- | --- |
| release_frame(*, ready_event=None) | 이 CudaAsync 묶음에서 원본 영상의 추가 읽기·수정을 하지 않음 |
| release_input(*, ready_event=None) | 모든 공유 입력을 더 이상 사용하지 않음. 단일 Step 계약 |
| current_source_cancel() | 현재 수신·디코딩 실행 문맥의 취소 이벤트 또는 None |

release_frame 뒤에도 독립 model_input·model_output으로 처리를 계속할 수 있습니다. 이벤트가 없으면 이미 모든 원본 읽기가 끝났다는 뜻입니다. 비동기 CUDA 읽기가 있으면 그 읽기를 모두 포함하는 이벤트가 필요합니다. 두 release 함수는 CudaAsync 밖에서는 아무 동작도 하지 않습니다.

```python
import torch
from pipeworks.execution import release_frame


def prepare(item, convert_to_independent_rgb):
    with torch.cuda.stream(item.cuda_stream):
        rgb = convert_to_independent_rgb(item.frame)
        ready = torch.cuda.Event()
        ready.record(item.cuda_stream)
    release_frame(ready_event=ready)
    return rgb
```

convert_to_independent_rgb는 사용자가 제공하는 함수이며 원본과 메모리를 공유하지 않는 GPU 결과를 만들어야 합니다. view나 원본 별칭만 만들고 해제 신호를 보내면 계약을 위반합니다. 이벤트는 CudaAsync가 기다리지 않고 완료 여부를 조회해 timeout 프레임을 안전하게 통과시킬 수 있는지 판단하는 데 사용합니다. 원본 메모리를 직접 삭제하거나 실행 중인 GPU 작업을 취소하지 않습니다.

current_source_cancel은 NvidiaDecode가 생산자에서 설정한 문맥을 RTSPSource가 읽는 데 사용합니다. 사용자 소스가 이를 활용한다면 None을 허용하고 is_set으로 종료를 확인하며 wait(timeout)으로 취소 가능한 대기를 구현합니다. 이 이벤트만으로 이미 진행 중인 외부 라이브러리의 블로킹 호출이 중단되지는 않습니다.

밑줄로 시작하는 ContextVar·scope·_DroppedFrame은 내부 실행기 계약입니다. 앱이 직접 만들거나 출력하지 않습니다. 요청별 scope는 finally에서 이전 문맥으로 복원됩니다. [CudaAsync](embedded/cuda_async.md)와 [사용자 Step](custom_steps.md)을 함께 확인하세요.
