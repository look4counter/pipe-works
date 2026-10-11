# 구현 계획

## 모듈 파일명 변경 계획

src/pipeworks/embedded/tensor_rt_pre_process.py를 tensor_rt_pre_process.py로 이동한다. embedded/__init__.py·단일 예제·좌표 변환 테스트·최적화 테스트·benchmark_preprocess.py의 import와 patch 경로를 바꾼다. 벤치마크의 HEAD 원본 조회는 새 경로를 우선하고 해당 리비전에 없으면 옛 경로를 사용한다. 현재 계약의 소스 경로를 갱신한다. 새 의존성·처리 동작 변경은 없으며 기존 검증을 사용한다. 헌법은 미작성 템플릿이고 한글 문서·speckit 절차를 준수한다.

## 좌표 복원 객체 후속 계획 (2026-10-11)

이 계획이 기존의 호출자 직접 복원 책임을 대체한다. Python 3.11.9와 기존 PyTorch만 사용한다. src/pipeworks/image_transform.py에 불변 ImageTransform을 정의하고 기존 정보 속성을 유지한다. restore_boxes_는 xyxy의 축별 뷰에 이동량 제거·배율 나누기·경계 제한을 수행한다. CPU 복사·추가 동기화·프레임 참조는 없다.

src/pipeworks/embedded/tensor_rt_pre_process.py는 이 객체를 생성한다. examples/step/tensor_rt_post_process.py의 _restore를 제거하고 메서드를 호출한다. 후처리는 shape와 restore_boxes_만 사용한다. tools/benchmark_postprocess.py도 새 객체를 사용한다.

tests/test_image_transform.py에서 세 모드·옵션·빈 결과·경계·추가 열·저장 공간을 검증하고 tests/test_tensor_rt_processing.py에서 대체 객체 위임을 확인한다. 기존 좌표 테스트를 갱신하고 전후처리·보고 회귀를 실행한다. 문서와 검증 기록을 갱신한다. 헌법은 미작성 템플릿이며 설계 전후 한글 문서·speckit 절차에 위반은 없다.


examples/step/tensor_rt_pre_process.py와 tensor_rt_post_process.py의 빈 파일을 구현한다. NV12 색 변환은 기존 local_yolo GPU 함수를 재사용하고 torch 보간·패딩으로 입력과 복원 정보를 만든다. 후처리는 Ultralytics NMS와 Boxes를 이용하여 BoxOverlay와 동일한 감지 계약을 제공한다. 결과는 GPU에 유지하고 원본 orig_img는 만들지 않는다. BoxOverlay는 Async 타임아웃으로 detections 속성이 없는 입력도 결과 누락으로 처리한다.

examples/01_single_stream_rtsp_style.py의 클래스명·plan 경로·불필요 batch 인자를 수정하고 examples/config/stream.yml에 두 단계 설정을 추가한다. tests/test_tensor_rt_processing.py는 실제 CUDA 합성 입력과 출력을 검증한다. test_box_overlay.py의 예제 순서 검증은 TensorRT 경로에 맞춘다. 실제 엔진 추론도 가능한 환경에서 검증한다. 헌법은 미작성 템플릿으로 원칙 검사를 생략한다.
## 스트림·버퍼 후속 계획

전처리 반복자에 장치별 모델 CUDA 스트림을 보관하고 영상 생산 완료 이벤트를 기록·대기한 뒤 변환한다. model_cuda_stream을 입력 생산자 정보로 전달하며 전처리 완료도 확인한다. TensorRTInference는 해당 스트림을 우선 사용한다. 후처리는 모델 스트림에서 NMS·복원을 수행하고 finally에서 완료 확인·임시 속성 및 지역 참조를 정리한다. 예외·출력 누락도 같은 정책을 사용한다. tests/test_tensor_rt_processing.py에 분리·정리 검증을 추가하고 실제 plan·Async를 검증한다.

## 범용 내장 전처리 구현 계획

Python 3.11.9와 기존 PyTorch 2.2.1 CUDA 연산을 사용하고 새 의존성을 추가하지 않는다. 헌장은 미작성 템플릿이므로 원칙 검사를 생략한다. 한글 문서·순차 speckit 절차를 준수하며 별도 연구가 필요한 미확정 사항은 없다.

src/pipeworks/embedded/tensor_rt_pre_process.py에 옵션 검증·생성자 기본값·GPU 색상 변환·크기 변환·정규화·출력 구성을 구현한다. 기존 NV12 변환을 src/pipeworks/image.py로 분리하고 local_yolo.py는 같은 함수를 기존 이름으로 가져와 YOLO와의 수치 계약을 보존한다. RGB/BGR HWC 입력은 FP32 CHW의 독립 저장 공간으로 변환한다. 모델 라이브러리를 가져오지 않는다.

모든 설정은 구성 검증을 마친 뒤 한 번에 적용한다. _set_config_defaults와 _resolve_config로 기존 설정 우선순위를 유지한다. letterbox는 round와 bilinear 보간·stride 나머지 패딩, stretch는 독립 가로·세로 배율, 중앙 자르기는 size를 채우는 배율과 음수 이동량을 사용한다. 연산은 FP32로 수행하고 마지막에 FP16/FP32 및 NCHW/NHWC를 연속 저장 공간으로 반환한다. 채널별 패딩은 새 GPU 버퍼를 채우고 리사이즈 결과를 복사한다.

별도 모델 스트림과 영상 준비 이벤트를 유지하고 독립 영상 변환 후 release_frame 이벤트를 보낸다. tensor_rt_transform은 기존 shape·ratio·left·top에 ratio_xy·output_shape·resize_mode를 추가한다. 기본 letterbox의 기존 후처리 계약은 유지하고 임의 설정에 맞는 후처리는 호출자의 책임이다.

embedded/__init__.py에서 내보내고 examples/step/tensor_rt_pre_process.py는 호환용 재수출만 남긴다. 단일 예제는 embedded에서 가져오며 examples/config/stream.yml에 기본 설정을 명시한다. README.md와 docs/pipeworks/embedded/tensor_rt_preprocess.md에 전체 옵션·탐지 및 분류 예제·입력 형식·수치 한계를 안내한다.

tests/test_tensor_rt_preprocess.py는 구성·YAML 우선순위·잘못된 입력 및 실제 CUDA 수치·스트림·수명·출력 사전을 검증한다. tests/test_tensor_rt_processing.py와 관련 Async·보고·프레임 수명·YOLO 검증을 실행한다. 환경의 기존 전체 실패는 구분해 기록하고 이번 변경으로 발생하는 실패를 해결한다.

## 전체 YAML 옵션 노출 계획

examples/config/stream.yml에 누락된 stride, scaleup, center, padding_value, crop_size, mean, std, input_name을 기본값으로 추가한다. 의미가 헷갈릴 수 있는 모드·최소 패딩·자르기·정규화·입력 이름은 짧은 한글 주석으로 안내한다. 기존 나머지 옵션 값은 유지한다. YAML을 읽어 생성자 시그니처의 키 전체와 대조하고 configure 결과가 기본 생성자와 같은지 검증한다. 동작 변경이 없으므로 새 테스트 파일이나 GPU 전체 검증은 추가하지 않는다.
