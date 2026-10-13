# YoloInference: YOLO 원시 추론 단계

`YoloInference`는 전처리가 만든 GPU `context.model_input`을 선택한 GPU 실행부로 실행하고 모든 원시 출력을 이름별 `context.model_output` 사전에 넣습니다. 특정 YOLO 라이브러리를 요구하지 않는 TorchScript 실행부와 사용자 실행부를 지원합니다. 색 변환·리사이즈·정규화·NMS·좌표 복원은 전후처리 단계에서 수행합니다. 원본 `frame`과 기존 `detections`를 읽거나 변경하지 않습니다. 전처리·후처리는 examples/step의 YOLO 예제 파일이 구현합니다.

`Pipeline.run()`은 이 단계를 포함한 모든 등록 단계에서 Batch 여부를 확인합니다. `batch=True`가 하나라도 있으면 전체 파이프라인을 중앙 프로세스에서 실행하고, 없으면 호출자 프로세스에서 실행합니다. `CudaAsync`, `EveryNFrames`, `TapSkipIfBusy`, `Hotswap` 내부도 같은 기준을 적용합니다. 두 실행 경로는 기존 추론 엔진과 단계 실행기를 재사용합니다.

## 연결

```python
from pipeworks.embedded import Backend, YoloInference

pipeline.step(preprocess_step)
pipeline.step(YoloInference('models/yolo11n.pt', backend=Backend.ULTRALYTICS, id='vehicle'))
pipeline.step(postprocess_step)
```

입력은 `gpu_id`와 같은 GPU의 텐서 또는 이름별 다중 GPU 입력 사전입니다. 이름은 비어 있지 않은 문자열이며 텐서는 1차원 이상이고 각 축이 양수여야 합니다. 채널 수·형상·자료형·색 순서는 공통 추론 단계에 고정하지 않고 모델 실행부의 규약을 따릅니다. 전처리가 크기와 정규화를 맞추고 비연속 입력은 GPU에서 연속화합니다. CPU·다른 GPU 입력은 거부합니다.

`cuda_stream`은 입력을 생산한 스트림이어야 합니다. 없으면 지정 GPU의 현재 스트림을 설정합니다. 추론은 준비 이벤트를 기다리고 GPU 작업 완료 후 결과를 전달합니다. 모델 실행 실패나 잘못된 입출력은 오류로 호출자에게 전달합니다.

```python
if context.model_output is not None:
    prediction = context.model_output['output0']
    consume(context.model_id, prediction)
```

출력은 선택 실행부의 모든 원시 GPU 텐서입니다. 사전 키는 보존하며 이름 없는 단일 텐서는 output0, 목록·튜플은 output0/output1 순서, 중첩 항목은 /로 연결한 경로를 사용합니다. 예를 들어 (prediction, {"features": [tensor]})는 output0과 output1/features/output0으로 전달합니다. 비텐서·빈 컨테이너·이름 충돌·CPU 출력은 오류입니다. 개별 실행에서는 스칼라·빈 출력 텐서도 허용합니다. 출력 형상은 모델에 따라 달라지며 NMS 여부도 내보낸 모델 자체의 계약을 따릅니다. 추론 단계는 추가 NMS를 적용하지 않습니다. 출력은 독립적으로 복제하여 다음 실행의 백엔드 버퍼 재사용으로 이전 결과가 바뀌지 않습니다.

## YOLO 전후처리 예제 연결

`examples`가 모듈 탐색 경로에 있을 때 새 YOLO 전후처리 예제를 연결합니다.

```python
from pipeworks.embedded import Backend, CudaAsync, YoloInference, YoloReport
from step.yolo_pre_process import YoloPreProcess
from step.yolo_post_process import YoloPostProcess

pipeline.step(CudaAsync(
    YoloPreProcess(),
    YoloInference('models/yolo11n.pt', backend=Backend.ULTRALYTICS, id='vehicle'),
    YoloPostProcess(),
    timeout_ms=100,
))
pipeline.step(YoloReport())
```

전처리는 GPU NV12 또는 HWC RGB/BGR `uint8` 이미지를 읽고 크기 변경·정규화 후 RGB NCHW 배치 1 텐서와 `image_transform`을 만듭니다. 원본 읽기 완료 이벤트로 프레임 해제를 알립니다. 기본은 640×640 letterbox, 패딩 114, 1/255 정규화, FP32입니다.

`YoloPreProcess`는 `Step`을 직접 상속하며 백엔드 중립 공통 도우미로 GPU 변환과 설정 검증을 제공합니다. TensorRT 전처리 예제 모듈에 의존하지 않습니다.

```python
YoloPreProcess(size=(640, 640), dtype="float16")
YoloPostProcess(names=["vehicle", "person"], classes=[0], confidence=0.4)
```

두 전처리의 `size`, `resize_mode`, `auto`, `stride`, `scaleup`, `center`, `padding_value`, `crop_size`, `color_order`, `scale`, `mean`, `std`, `dtype`, `layout`, `input_name`은 생성자와 `YoloPreProcess` YAML 섹션에서 지정합니다. 크기 변경·정규화의 의미는 [기존 GPU 전처리 안내](tensor_rt_preprocess.md)와 같습니다. 기본은 RGB NCHW 텐서이며 `input_name='images'`를 지정하면 이름별 입력 사전을 만듭니다. 색 순서와 배치는 모델 요구에 맞게 선택합니다. Ultralytics 호환 실행부에는 RGB NCHW FP32/FP16 입력을 사용합니다. 다른 실행부는 해당 모델 규약을 따릅니다.

후처리는 FP32/FP16 `(1, 4+클래스수, N)` 원시 감지 예측을 신뢰도·클래스로 필터링하고 GPU NMS와 좌표 복원을 수행합니다. `detections[model_id]`에 `boxes`, `names`, `orig_shape`를 기록합니다. 실행하지 않은 입력은 해당 ID의 `None`, 감지 없음은 빈 `boxes` 결과이며 다른 모델 결과는 보존합니다. 후처리 종료 시 `model_input`, `model_output`, `image_transform`, `model_id`, `_inference_profile`을 정리합니다.

| 후처리 설정 | 기본값 | 의미 |
| --- | --- | --- |
| `confidence` | `0.25` | 0~1 신뢰도 임계값 |
| `iou` | `0.7` | 0~1 NMS IoU 임계값 |
| `classes` | `None` | 모든 클래스. 선택 시 정수 ID 목록 |
| `max_det` | `300` | 최대 감지 수 |
| `output_name` | `output0` | 원시 출력 사전의 키 |
| `names` | `None` | 기본 COCO 이름. 사용자 이름 목록 또는 연속 정수 키 사전 |
| `end2end` | `False` | 이미 NMS를 포함한 `(1,N,6)` 출력이면 `True` |

```yaml
YoloPreProcess:
  size: [640, 640]
  dtype: float32
YoloPostProcess:
  confidence: 0.25
  iou: 0.7
  classes: null
  max_det: 300
```

사용자 감지 모델은 `names`를 맞춰야 합니다. 이미 NMS를 포함한 출력은 `end2end=True`로 설정하며 추가 NMS 없이 필터링하고 좌표를 복원합니다. 분할·포즈와 컨텍스트당 여러 이미지의 결과 해석은 모델별 후처리를 작성해야 합니다.

## 설정

```python
YoloInference(
    'models/yolo11n.pt',
    backend=Backend.ULTRALYTICS,
    batch=False,
    gpu_id=0,
    id=None,
    profile_index=0,
)
```

| 설정 | 기본값 | 의미 |
| --- | --- | --- |
| `backend` | 필수 | `Backend.TENSORRT`, `Backend.TORCHSCRIPT`, `Backend.ULTRALYTICS` 또는 사용자 모듈:클래스 경로 |
| `profile_index` | `0` | TensorRT 최적화 프로파일 번호. 다른 실행부는 0만 허용 |
| `batch` | `False` | 생성자에서만 지정하는 공유 배치 모드 |
| `gpu_id` | `0` | 음수가 아닌 GPU 번호 |
| `id` | `None` | 실행 식별자. 생략/null이면 확장자를 포함한 모델 파일명 |

```yaml
YoloInference:
  backend: ultralytics
  gpu_id: 0
  id: vehicle
```

YAML이 생성자 기본값보다 우선하며 키를 제거하면 생성자 값으로 돌아갑니다. `id`는 공백뿐인 값이 아닌 문자열이어야 합니다. `classes`와 `confidence`는 후처리에 설정합니다.

추론 단계는 전달받은 모든 입력을 실행합니다. 실행 간격은 [EveryNFrames](every_n_frames.md)의 `interval_frames`로 지정하며 전처리·추론·후처리를 함께 감싸면 생략 프레임의 전처리 비용도 줄일 수 있습니다. 삭제된 `inference_interval_frame` 생성자 인자와 YAML 키는 오류로 거부합니다.

## 공유 배치와 보고

`batch=True`이면 각 입력 텐서의 첫 축이 1이어야 합니다. 같은 모델 경로·실행부·GPU·입력 이름·자료형·비배치 형상의 요청만 결합합니다. 모든 출력의 첫 축이 요청 수와 같아야 하며 그렇지 않은 출력은 분리할 수 없어 오류로 처리합니다. 각 출력의 요청별 GPU 복사본을 반환합니다. ID는 공유 조건에 영향을 주지 않습니다. 공유 워커는 준비된 모델 입력만 처리하며 전후처리는 호출자가 연결합니다.

모델과 같은 위치의 같은 이름 `.yml`에 기존 YOLO 배치 설정을 지정합니다. 파일이 없으면 배치 크기 1과 대기 0을 사용합니다.

```yaml
max_batch_size: 4
timeout_ms: 10
```

오류가 발생한 배치의 모든 요청은 오류를 받고 다음 요청에서 모델을 다시 준비합니다. 준비된 작업자는 기존 경로 캐시 규칙에 따라 재사용합니다. `CudaAsync`, `YoloReport`, `StreamReport`와 연결할 수 있습니다.

두 계열의 전후처리는 공통 프로파일을 공유하고 실제 추론 백엔드에 연결합니다. `YoloReport`에서 전처리·추론·후처리와 전체 시간을 완료 표본 하나로 확인할 수 있습니다. 건너뜀·오류·비동기 부분 종료도 기록합니다. `YoloInference` 단독 사용은 자체 추론 보고 동작을 유지합니다. 전후처리 클래스 이름과 관계없이 모든 backend 실행은 YoloReport에 전처리·추론·후처리를 한 표본으로 기록합니다.

## 공통 계약과 추론 교체

두 계열의 전후처리는 같은 구현·생성자 옵션·기본값을 사용하고 각각 Step을 직접 상속합니다. 같은 YOLO 모델의 전처리 규칙과 출력 스키마라면 전후처리를 유지하고 추론 단계만 교체할 수 있습니다.

| 필드 | 공통 의미 |
| --- | --- |
| `model_input` | GPU 텐서 또는 이름별 GPU 입력 사전 |
| `model_output` | 이름별 원시 GPU 출력 사전 |
| `model_id` | 실행 식별자 |
| `image_transform` | 원본 좌표 복원 정보 |
| `detections[model_id]` | 후처리 감지 결과 |

```python
from pipeworks.embedded import Backend, CudaAsync, YoloInference
from pipeworks.embedded import YoloReport
from step.yolo_pre_process import YoloPreProcess
from step.yolo_post_process import YoloPostProcess

inference = YoloInference('models/yolo11n.pt', backend=Backend.ULTRALYTICS, batch=True, id='vehicle')
# 아래 추론으로 교체해도 전후처리는 같습니다.
# inference = YoloInference('models/yolo11n.plan', backend=Backend.TENSORRT, batch=True, id='vehicle')

pipeline.step(CudaAsync(
    YoloPreProcess(), inference, YoloPostProcess(), timeout_ms=100,
))
pipeline.step(YoloReport())
```

TensorRTPreProcess와 TensorRTPostProcess를 사용해도 같은 계약으로 연결됩니다. 실제 입력 자료형·형상·입출력 이름은 모델 요구를 따라야 합니다. Ultralytics 주 감지 예측은 output0이고 이름 있는 실행부와 TensorRT는 실제 출력 이름을 사용하므로 필요한 경우 후처리 output_name을 맞춥니다. TensorRT와 YoloInference는 다중 입력을 전달할 수 있으며 선택한 실행부와 모델이 그 입력을 지원해야 합니다. Ultralytics 체크포인트 어댑터는 단일 이미지 입력만 지원합니다.

두 후처리의 기본 classes는 None으로 모든 클래스입니다. 기존 TensorRT 예제의 차량 필터가 필요하면 classes=[2]를 명시합니다. 두 후처리는 FP16·사용자 names·end2end 옵션을 동일하게 지원합니다.

기존 사용자 단계가 만든 yolo_transform/tensor_rt_transform은 image_transform이 없을 때 읽을 수 있습니다. 이전 내부 프로파일도 입력 호환으로 처리합니다. 새 전처리는 공통 필드만 생성하고 후처리는 공통 및 이전 임시 필드를 모두 정리합니다.

## 실행부 선택과 GPU 전용 계약

backend=Backend.TORCHSCRIPT는 torch.jit.save로 저장된 모델을 CUDA로 로드합니다. 일반 체크포인트 .pt와 TorchScript 파일은 확장자만으로 구별하지 않습니다. 기존 yolo11n.pt는 backend=Backend.ULTRALYTICS를 명시해야 합니다. 실행 형식 자동 탐색이나 CPU 대체 실행은 제공하지 않습니다.

Ultralytics 호환 실행부는 체크포인트의 PyTorch 모델을 CUDA에서 직접 호출하며 AutoBackend·NumPy 변환을 사용하지 않습니다. 해당 라이브러리는 이 실행부를 선택할 때만 가져옵니다. 감지의 주 예측 output0은 유지하며 보조 GPU 텐서도 함께 전달합니다.

GPU 전용은 영상·모델 텐서 연산과 결과 전달에 적용합니다. 파이프라인 제어, 파일 역직렬화와 정적 모델 메타데이터는 CPU에서 처리합니다. 실행 중 PyTorch 연산을 감시하여 CPU 텐서·다른 GPU·CPU 장치 전환·입력 데이터의 scalar 읽기를 거부합니다. TorchScript 정적 스칼라 상수와 모델의 고정 stride는 메타데이터로 허용합니다. GPU 감시와 모든 출력 복제로 실행 비용과 메모리 사용이 늘 수 있습니다.

커스텀 네이티브 실행부가 내부에서 직접 수행하는 연산은 PyTorch 감시 범위 밖이므로 그 구현도 GPU 전용 계약을 지켜야 합니다. 새 실행부가 반환하는 CPU 출력은 GPU로 자동 이동하지 않고 거부합니다. 특정 YOLO 라이브러리에서 독립적인 범위는 추론 단계입니다. 현재 감지 후처리 예제는 Ultralytics 결과 타입·기본 COCO 이름을 사용하므로 완전히 독립적인 구성에는 자체 후처리를 연결합니다.

## 사용자 실행부 연결

backend="my_project.backends:MyYoloBackend"처럼 모듈:클래스로 지정합니다. 모듈은 파이프라인 실행 프로세스에서 가져올 수 있어야 합니다. 생성자는 model_path와 gpu_id 두 인자를 받고 infer(inputs)를 제공해야 합니다.

```python
class MyYoloBackend:
    def __init__(self, model_path, gpu_id):
        self.model = load_my_gpu_model(model_path, gpu_id)

    def infer(self, inputs):
        return self.model(**inputs)  # 이름별 GPU 텐서 입력 및 GPU 출력

pipeline.step(YoloInference(
    'models/custom.pt', backend='my_project.backends:MyYoloBackend',
))
```

TorchScript는 단일 텐서를 위치 인자로, 입력 사전을 이름 있는 인자로 전달합니다. 추론 단계는 리사이즈·정규화·출력 형식 변환·NMS를 추가하지 않습니다. 분할·포즈·특수 출력 해석은 해당 모델의 후처리가 담당합니다. 모든 출력의 첫 축이 결합 배치 수와 같을 때만 공유 배치를 사용합니다.

`Backend`는 `pipeworks`와 `pipeworks.embedded`에서 가져올 수 있는 문자열 enum입니다. 생성자에서 `backend`는 반드시 지정해야 하며 생략하면 `TypeError`가 발생합니다. YAML에서는 `torchscript` 또는 `ultralytics` 문자열을 사용하며 설정을 제거하면 생성자 선택으로 복원됩니다.

## TensorRT 실행 통합

```python
from pipeworks import Backend
from pipeworks.embedded import YoloInference, YoloReport

inference = YoloInference(
    "models/yolo11n.plan",
    backend=Backend.TENSORRT,
    profile_index=0,
    batch=True,
)
```

TensorRT 실행도 동일한 model_input·model_output·model_id 계약을 사용합니다. 엔진의 실제 입출력 이름·자료형·형상과 동적 프로파일 범위는 그대로 검증하며 플러그인 및 모델별 배치 설정은 [TensorRT 엔진 안내](tensor_rt_inference.md)를 따릅니다. YAML 설정은 YoloInference 섹션에서 backend: tensorrt와 profile_index를 지정합니다. 전후처리는 유지하고 추론 backend만 바꿀 수 있습니다. YoloReport에서 전후처리·추론 표본을 확인하며 CudaAsync의 timeout/busy도 TensorRT로 기록합니다.


## 전후처리 구현 위치

영상 처리 구현은 examples/step/yolo_pre_process.py와 yolo_post_process.py가 소유합니다. 전처리 파일에 NV12 변환과 ImageTransform이 포함되고 후처리 파일에 필터·NMS·좌표 복원과 감지 결과 생성이 포함됩니다. 코어는 준비된 GPU 텐서의 추론과 컨텍스트 연결만 담당하며 예제 전후처리를 가져오지 않습니다. TensorRT 이름의 전후처리 예제도 같은 구현을 재사용하므로 모델 입력/출력 규약이 맞으면 backend에 관계없이 연결할 수 있습니다.
