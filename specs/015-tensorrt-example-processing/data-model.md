# 범용 전처리 데이터 계약

YoloDetect.id도 파일명 기본값과 생성자/YAML 설정을 따른다. YOLO 결과는 공통 detections[id]의 Ultralytics 결과 객체 또는 None이다. 원본 해상도의 orig_img·orig_shape·boxes는 유지한다. YOLO는 내부 후처리까지 완료하므로 임시 model_id가 필요하지 않다.

## 모델 ID와 결과 사전

TensorRTInference.id는 유효한 문자열이며 기본값은 모델 파일명이다. 입력 컨텍스트의 model_id는 후처리까지 전달하고 완료 후 제거한다. detections는 {ID: 탐지 결과 또는 None}이며 결과의 boxes·names·orig_shape 구조는 유지한다. 후처리는 사전을 복사하고 현재 키만 교체한다. 전처리는 결과 사전을 유지한다. Overlay는 ID별 박스 복사와 CUDA 완료 이벤트를 보관한다.

모듈 파일명 변경은 데이터·클래스·변환 객체 계약을 바꾸지 않는다. 현재 가져오기 경로는 examples를 모듈 탐색 경로에 둔 step.tensor_rt_pre_process다. 내장 전처리 내보내기는 제거한다. 제공 YAML에는 전처리 섹션이 없으며 기본 예제는 생성자 기본값을 사용한다.

## 복원 기능을 가진 변환 객체

ImageTransform은 아래 정보를 불변으로 보관하고 ratio는 ratio_xy에서 계산한다. restore_boxes_(boxes)는 모델 입력 픽셀 좌표의 N×4 이상 실수 텐서 앞 네 xyxy 열만 원본 경계로 제자리 복원한다. 장치·자료형·추가 열·저장 공간을 유지하고 같은 텐서를 반환한다. 후처리 계약은 shape와 restore_boxes_뿐이며 수명·정리는 기존과 같다.


- 입력 컨텍스트: frame은 GPU uint8 이미지이며 pixel_format은 NV12, RGB 또는 BGR이다. cuda_stream은 입력 생산 스트림이다. NV12는 video_stream.codec_context의 height·width를 사용한다. RGB/BGR은 HWC 텐서 자체의 크기를 사용한다.
- 생성자 기본값: 최초 옵션을 깊은 복사해 보관한다. YAML은 일부 옵션을 덮어쓰고 제거된 옵션은 최초 값으로 돌아간다.
- model_input: 기본적으로 배치 크기 1의 연속 GPU 텐서다. input_name을 지정하면 한 항목의 이름별 텐서 사전이다. dtype은 float32 또는 float16이며 layout은 nchw 또는 nhwc다.
- cuda_stream: 전처리·직접 추론·후처리에 사용하는 컨텍스트 CUDA 스트림이다. 기존 객체를 보존하며 생략 시 현재 GPU 스트림을 저장한다.
- tensor_rt_transform: shape는 원본 높이·너비, ratio_xy는 가로·세로 배율, left·top은 패딩 또는 음수 자르기 이동량, output_shape는 최종 높이·너비다. ratio는 균일 배율이면 기존 scalar이고 비균일이면 가로·세로 쌍이다. resize_mode로 변환 종류를 구분한다.
- 프레임 수명: 원본 읽기는 독립 FP32 이미지 생성 이후 끝난다. release_frame 이벤트가 해당 읽기 완료를 보장한다. 출력 영상과 후속 모델 입력은 원본 저장 공간을 공유하지 않는다.

## 표시·후처리 내부 기본값

BoxOverlay의 생성자 기본값은 전체 ID·초록색·두께 2·이전 결과 유지다. TensorRTPostProcess는 독립 classes=[2] 목록·신뢰도 0.25·IoU 0.7·최대 300·output0을 사용한다. 빈 configure는 이 내부 기본값으로 복원하며 제공 YAML에는 두 섹션이 없다. 기존 탐지 결과·좌표 변환·수명 계약은 바꾸지 않는다.
