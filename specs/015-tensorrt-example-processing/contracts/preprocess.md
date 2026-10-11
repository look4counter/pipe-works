# TensorRTPreProcess 공개 계약

src/pipeworks/embedded/tensor_rt_pre_process.py 및 pipeworks.embedded에서 같은 Step 클래스를 제공한다. 기존 예제 모듈도 같은 클래스를 재수출한다.

| 옵션 | 기본값 | 조건 |
| --- | --- | --- |
| size | [640, 640] | 양의 정수 높이·너비 |
| resize_mode | letterbox | letterbox, stretch, resize_center_crop |
| auto | false | letterbox에서만 true 허용 |
| stride | 32 | 양의 정수 |
| scaleup | true | 불리언, letterbox에서 확대 제한 |
| center | true | 불리언, letterbox 패딩 위치 |
| padding_value | 114 | 정규화 전 0~255 스칼라 또는 3채널 값 |
| crop_size | null | 중앙 자르기 모드에서만 지정, 기본 size, size 이하 |
| color_order | rgb | rgb 또는 bgr |
| scale | 1/255 | 유한한 숫자 |
| mean | [0, 0, 0] | 유한한 채널별 3개 값 |
| std | [1, 1, 1] | 유한한 양수 채널별 3개 값 |
| dtype | float32 | float32 또는 float16 |
| layout | nchw | nchw 또는 nhwc |
| input_name | null | null 또는 비어 있지 않은 문자열 |

configure의 잘못된 옵션 이름과 잘못된 옵션 값은 ValueError로 거부한다. 생성자의 알 수 없는 키워드는 Python의 표준 TypeError를 따른다. 생성자와 YAML의 동일 옵션을 지원하고 모든 값은 검증을 마친 뒤 적용한다. RGB/BGR·평균·표준편차·패딩 채널은 출력 color_order를 기준으로 한다. 정규화는 (pixel × scale − mean) / std이다. 보간과 정규화 계산은 FP32이며 최종 출력 자료형을 변환한다.

입력은 GPU uint8 NV12 또는 HWC RGB/BGR이며 오류 형식·장치·크기는 ValueError로 거부한다. 성공 시 같은 컨텍스트를 반환하고 model_input·model_cuda_stream·tensor_rt_transform을 추가하며 기존 detections를 초기화한다. 원본 frame은 수정하지 않는다. CPU나 NumPy 이미지를 자동 업로드하지 않는다.
