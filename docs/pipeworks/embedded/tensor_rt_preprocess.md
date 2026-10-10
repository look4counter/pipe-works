# TensorRTPreProcess: 범용 GPU 이미지 전처리

`TensorRTPreProcess`는 이미지 모델이 요구하는 크기·색상·정규화·자료형·텐서 배치를 구성합니다. Ultralytics를 호출하지 않고 PyTorch CUDA 연산으로 수행하며 TensorRT 엔진을 읽거나 전처리 규칙을 추측하지 않습니다.

```python
from pipeworks.embedded import TensorRTPreProcess

preprocess = TensorRTPreProcess(
    size=(640, 640),
    resize_mode="letterbox",
    dtype="float16",
)
pipeline.step(preprocess)
```

## 입력과 출력

`context.frame`은 GPU의 uint8 이미지입니다. `context.pixel_format`으로 입력을 구분합니다.

- `NV12`: 기존 디코더의 압축 배치 텐서입니다. `video_stream.codec_context.height/width`를 사용하며 양의 짝수 크기가 필요합니다. 2차원 텐서 및 정확한 크기의 1차원 텐서를 받습니다.
- `RGB` 또는 `BGR`: `[높이, 너비, 3]`의 HWC 텐서입니다. 크기는 텐서에서 읽습니다. 대소문자는 구분하지 않습니다.

입력 생산 스트림은 `context.cuda_stream`이며 없으면 해당 GPU의 현재 스트림을 사용합니다. 원본 프레임과 기존 영상 스트림을 보존하고 이미지 데이터를 CPU로 복사하지 않습니다. CPU/NumPy 이미지를 자동으로 업로드하지 않습니다.

출력은 `context.model_input`에 배치 크기 1의 연속 GPU 텐서로 저장합니다. 기본 형상은 `[1, 3, 640, 640]`입니다. `input_name="images"`를 지정하면 `{"images": tensor}` 사전을 만듭니다. 다중 입력 모델의 나머지 입력은 다른 단계가 추가해야 합니다. `TensorRTInference(batch=True)`는 각 요청의 동일 형상 텐서를 첫 번째 축으로 묶습니다.

`context.model_cuda_stream`에는 모델 작업 스트림, `context.tensor_rt_transform`에는 좌표 변환 정보를 저장합니다. 기존 `detections`는 초기화합니다. 원본 읽기가 끝난 시점에 CUDA 완료 이벤트와 함께 `release_frame()`을 호출해 CudaAsync의 프레임 수명 계약을 유지합니다.

## 옵션

모든 옵션은 선택적 생성자 인자와 YAML의 `TensorRTPreProcess` 섹션에서 지정할 수 있습니다. 같은 옵션이 있으면 YAML이 우선합니다. YAML에서 제거한 옵션은 최초 생성자 값으로 돌아갑니다. 잘못된 옵션 이름·값은 구성 오류로 거부하며 검증 실패 시 부분적으로 적용하지 않습니다.

| 옵션 | 기본값 | 설명 |
| --- | --- | --- |
| `size` | `[640, 640]` | 양의 정수 `[높이, 너비]` |
| `resize_mode` | `letterbox` | `letterbox`, `stretch`, `resize_center_crop` |
| `auto` | `false` | LetterBox에서 남은 패딩의 stride 나머지만 사용 |
| `stride` | `32` | 양의 정수, `auto=true`의 패딩 계산 기준 |
| `scaleup` | `true` | LetterBox에서 작은 이미지 확대 허용 |
| `center` | `true` | LetterBox 중앙 배치, false이면 왼쪽 위 배치 |
| `padding_value` | `114` | 정규화 전 0~255 스칼라 또는 채널별 3개 값 |
| `crop_size` | `null` | 중앙 자르기 출력 `[높이, 너비]`, 생략하면 size |
| `color_order` | `rgb` | 출력 채널 순서 `rgb` 또는 `bgr` |
| `scale` | `1/255` | 픽셀 값에 곱할 유한한 숫자 |
| `mean` | `[0, 0, 0]` | 유한한 채널별 평균 |
| `std` | `[1, 1, 1]` | 유한한 양수 채널별 표준편차 |
| `dtype` | `float32` | 출력 `float32` 또는 `float16` |
| `layout` | `nchw` | 출력 `nchw` 또는 `nhwc` |
| `input_name` | `null` | 출력 사전의 입력 이름, 생략하면 단일 텐서 |

정규화는 `(pixel × scale − mean) / std`이며 평균·표준편차·패딩의 채널별 값은 출력 `color_order` 순서입니다. NV12 변환에 포함된 정규화를 내부에서 환산하므로 `/255`가 중복 적용되지 않습니다. 보간과 정규화는 FP32로 계산한 뒤 마지막에 출력 자료형을 변환합니다.

## 크기 변경 방식

`letterbox`는 종횡비를 유지하고 남은 공간을 패딩합니다. `auto=true`이면 출력이 항상 size인 것은 아닙니다. size=[640,640], stride=32의 1920×1080 영상은 높이 384·너비 640이 됩니다. 고정 640×640 엔진에는 `auto=false`를 사용합니다. size 자체를 stride 배수로 강제하지 않습니다.

`stretch`는 종횡비를 유지하지 않고 size에 맞춥니다.

`resize_center_crop`은 size의 높이·너비를 모두 채우도록 비율을 유지해 리사이즈한 뒤 crop_size를 중앙에서 자릅니다. crop_size는 size보다 클 수 없습니다. 예를 들어 size=[256,256], crop_size=[224,224]는 짧은 변을 256으로 리사이즈한 뒤 224×224를 자릅니다.

`auto`, `stride`, `scaleup`, `center`, `padding_value`는 LetterBox에서만 결과에 영향을 줍니다. 다른 모드의 `auto=true` 및 중앙 자르기 밖의 `crop_size` 지정은 거부합니다. 다른 모드에서 중앙 자르기로 바꿀 때 크기 설정도 함께 지정하고, 자르기 모드에서 다른 모드로 바꿀 때는 `crop_size: null`로 해제합니다.

## 탐지용 설정 예제

```yaml
TensorRTPreProcess:
  size: [640, 640]
  resize_mode: letterbox
  auto: false
  stride: 32
  scaleup: true
  center: true
  padding_value: 114
  color_order: rgb
  scale: 0.00392156862745098
  mean: [0, 0, 0]
  std: [1, 1, 1]
  dtype: float32
  layout: nchw
```

## 분류용 설정 예제

다음은 해당 입력 규칙을 요구하는 모델에 적용할 수 있는 예시이며 실제 모델의 학습·내보내기 계약을 확인해야 합니다.

```yaml
TensorRTPreProcess:
  size: [256, 256]
  resize_mode: resize_center_crop
  crop_size: [224, 224]
  color_order: rgb
  scale: 0.00392156862745098
  mean: [0.485, 0.456, 0.406]
  std: [0.229, 0.224, 0.225]
  dtype: float32
  layout: nchw
  input_name: pixels
```

## 좌표와 수치 계약

`tensor_rt_transform.shape`는 원본 높이·너비, `ratio_xy`는 가로·세로 배율, `left/top`은 패딩 이동량입니다. 중앙 자르기에서는 이동량이 음수입니다. 원본 좌표는 `(변환된 좌표 − 이동량) / 해당 축의 배율`로 복원합니다. `output_shape`는 최종 높이·너비이고 `resize_mode`로 변환 종류를 구분합니다. 기존 `ratio`는 균일 배율이면 숫자, 비균일 배율이면 가로·세로 쌍입니다.

기본 LetterBox는 기존 YOLO 후처리 예제와 호환됩니다. stretch·다른 색상·정규화·레이아웃을 선택한 모델은 해당 모델의 출력 해석에 맞는 후처리가 필요합니다.

기존 GPU NV12 색 변환과 bilinear 보간을 사용합니다. CPU OpenCV의 uint8 리사이즈·반올림과 비트 단위로 같은 결과를 보장하지 않습니다. 모델 입력 크기·자료형·배치 형식과 TensorRT 동적 프로파일 범위는 호출자가 맞춰야 합니다.
