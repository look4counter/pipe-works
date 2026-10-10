# 범용 전처리 데이터 계약

- 입력 컨텍스트: frame은 GPU uint8 이미지이며 pixel_format은 NV12, RGB 또는 BGR이다. cuda_stream은 입력 생산 스트림이다. NV12는 video_stream.codec_context의 height·width를 사용한다. RGB/BGR은 HWC 텐서 자체의 크기를 사용한다.
- 생성자 기본값: 최초 옵션을 깊은 복사해 보관한다. YAML은 일부 옵션을 덮어쓰고 제거된 옵션은 최초 값으로 돌아간다.
- model_input: 기본적으로 배치 크기 1의 연속 GPU 텐서다. input_name을 지정하면 한 항목의 이름별 텐서 사전이다. dtype은 float32 또는 float16이며 layout은 nchw 또는 nhwc다.
- model_cuda_stream: 독립 모델 스트림 또는 현재 비동기 실행 범위의 모델 스트림이다. 원본 cuda_stream은 보존한다.
- tensor_rt_transform: shape는 원본 높이·너비, ratio_xy는 가로·세로 배율, left·top은 패딩 또는 음수 자르기 이동량, output_shape는 최종 높이·너비다. ratio는 균일 배율이면 기존 scalar이고 비균일이면 가로·세로 쌍이다. resize_mode로 변환 종류를 구분한다.
- 프레임 수명: 원본 읽기는 독립 FP32 이미지 생성 이후 끝난다. release_frame 이벤트가 해당 읽기 완료를 보장한다. 출력 영상과 후속 모델 입력은 원본 저장 공간을 공유하지 않는다.
