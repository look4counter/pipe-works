# 구현 계획

## 표시·후처리 클래스 내부 설정 계획

Python 3.11·기존 PyTorch·Ultralytics·unittest를 유지한다. 헌법은 미작성 템플릿이므로 검사 규칙은 없으며 한글 문서·speckit 절차를 준수한다. 기존 _set_config_defaults와 _resolve_config를 재사용해 생성자 내부에 기본값을 모으고 configure는 이 값을 검증·적용한다. 새 생성자 옵션은 추가하지 않는다.

examples/step/box_overlay.py의 생성자에 line_width=2, line_color="#00ff00", keep_previous=True, id=None을 둔다. examples/step/tensor_rt_post_process.py는 클래스 이름 로드 후 confidence=0.25, iou=0.7, classes=[2], max_det=300, output_name="output0"을 내부 기본값으로 둔다. 깊은 복사로 클래스 목록을 분리한다. 기존 GPU 실행 알고리즘은 변경하지 않는다.

examples/config/stream.yml의 두 섹션만 제거하고 다른 설정은 바이트 단위로 보존한다. tests/test_box_overlay.py는 YAML 섹션 대신 기본 표시 설정을 검증한다. tests/test_tensor_rt_processing.py는 CPU 구성 검증과 기존 GPU 혼합 클래스 입력에서 기본 [2] 필터를 확인한다. 전체 클래스 처리를 명시적으로 검증하는 기존 최적화 테스트는 classes=None을 직접 구성한다. docs/pipeworks/embedded/tensor_rt_inference.md·yolo_detect.md와 모델 ID 계약을 내부 기본값 안내로 갱신한다.

기본값·빈 구성 복원·인스턴스 목록 격리·제공 YAML·예제 구성과 후처리·Overlay·모델 ID·보고·전처리 회귀를 실행하고 git diff --check와 수렴 점검을 수행한다. 설계 전후 원칙 위반은 없다. 과거 계획의 두 예제 YAML 노출 부분은 이 계획으로 대체한다.

## 전처리 예제 분리 구현 계획 (2026-10-11)

이번 계획은 아래 과거 계획의 내장 전처리 공개·예제 재수출·전체 옵션 YAML 노출 부분을 대체한다.

### 기술 맥락과 원칙 검토

Python 3.11.9·PyTorch 2.2.1·기존 unittest와 CUDA 환경을 유지하며 의존성을 추가하지 않는다. 헌법은 미작성 템플릿이므로 원칙 검사는 생략한다. 한글 문서와 지정된 speckit 순서를 준수하며 설계 전후 위반은 없다. 실행 성능과 수치·원본 수명은 그대로 보존한다.

### 구현 구조

src/pipeworks/embedded/tensor_rt_pre_process.py의 구현을 examples/step/tensor_rt_pre_process.py로 이동한다. embedded/__init__.py의 import와 __all__ 항목을 제거한다. 예제는 step.tensor_rt_pre_process에서 가져온다. configure와 생성자 옵션은 유지한다. 공통 image·ImageTransform·계측·실행 유틸리티는 기존 라이브러리에서 사용한다. CudaAsync의 클래스명 기반 계측은 이동의 영향을 받지 않아 변경하지 않는다.

테스트와 benchmark_preprocess.py에 examples 경로를 추가하고 예제 클래스에서 가져온다. 최적화 테스트의 patch 경로도 변경한다. 이전 재수출 동일성 테스트는 예제 구현의 위치·내장 비공개·제공 YAML 없이 기본 구성 가능한 계약 검증으로 바꾼다. 벤치마크의 HEAD 비교 대상은 예제 경로를 먼저 찾고 과거 두 내장 파일명으로 순차 대체한다.

examples/config/stream.yml에서 TensorRTPreProcess 섹션만 삭제한다. 다른 섹션의 사용자 편집은 보존한다. README·전처리·추론 안내는 예제 가져오기와 생성자 기반 설정으로 갱신한다. 기존 문서 파일 위치는 링크 보존을 위해 유지한다.

### 검증과 단계

구현 이동 전에 새 공개 위치 계약 테스트를 갱신하고 실패를 확인한다. 이동 뒤 전처리·좌표 복원·후처리·모델 ID·보고·프레임 해제·CudaAsync 회귀를 실행한다. 예제 YAML과 생성자 기본값, 내장 모듈 제거·import 누락, 벤치마크 과거 경로 탐색과 git diff --check를 확인한다. CUDA 또는 엔진이 없는 환경의 건너뜀은 명시하고 기존 실패와 구분한다. 명세·계획·작업을 분석한 뒤 구현하고 수렴 점검으로 남은 요구를 확인한다.

## YOLO 공통 ID 후속 구현 계획

기존 Python·PyTorch·Ultralytics를 사용하고 의존성을 추가하지 않는다. src/pipeworks/embedded/yolo_detect.py에 id 구성·검증을 추가한다. 입력마다 기존 사전을 얕게 복사하고 현재 ID에 None을 넣는 공통 메서드가 ID를 반환한다. 두 실행 경로는 해당 ID에 결과를 저장하여 설정 변경 중에도 시작한 입력의 ID를 유지한다. local_yolo와 엔진 공유 키는 바꾸지 않는다. 원본과 GPU 결과 텐서를 복제하지 않는다.

tests/test_yolo_detect.py·test_yolo_batch.py의 결과 읽기를 사전 계약으로 변경한다. tests/test_yolo_model_ids.py에서 설정·실행 중 ID 변경·직렬 결과·혼합 결과 보존·오류·비동기 격리·Overlay 소비를 검증한다. 실제 모델 검증은 기존 YOLO 테스트를 사용한다. docs/pipeworks/embedded/yolo_detect.md·models.md·README.md·examples/config/stream.yml과 공통 계약을 갱신한다. 기존 개별 오류 전파·배치 오류 통과 정책을 유지한다. 헌법은 미작성 템플릿이며 설계 전후 한글 문서·speckit 절차에 위반은 없다.

## 직렬 모델 식별 구현 계획

기존 Python·PyTorch·TensorRT를 사용하고 새 의존성을 추가하지 않는다. tensor_rt_inference.py의 생성자·configure에 id를 추가하고 원자적 검증 뒤 설정한다. process 입력 전달 시 model_id를 설정하여 배치/개별/간격 경로 모두 지원한다. 엔진 공유 키에는 ID를 넣지 않는다.

tensor_rt_pre_process.py의 detections 초기화를 제거한다. tensor_rt_post_process.py는 기존 사전을 얕게 복사한 새 사전에 현재 ID 결과만 넣어 CudaAsync 작업 컨텍스트의 원본 결과 오염을 방지한다. model_id는 finally에서 정리한다. 출력이 존재하면 유효한 model_id가 필수이며 사용자 모의 출력도 이 계약을 따른다.

examples/step/box_overlay.py의 id 선택과 ID별 GPU 박스·완료 이벤트 캐시를 구현한다. 기존 단일 YOLO 결과는 별도 캐시 키로 처리한다. geometry/device/선택 ID가 바뀌면 캐시를 초기화한다. None은 keep_previous 정책을 적용하고 빈 결과는 이전 박스를 지운다. 모델 결과 사전을 합치는 과정은 GPU에서 수행한다.

기존 전후처리 테스트·벤치마크의 결과 읽기를 갱신하고 tests/test_tensor_rt_model_ids.py에서 ID 설정·간격·배치·직렬 실제 엔진·사전 격리·오류 정리·Overlay 선택과 ID별 이전 결과를 검증한다. 기존 추론·Overlay·성능 보고·비동기 테스트를 실행한다. 문서·예제 YAML을 갱신하고 모든 Overlay는 직렬 추론 뒤에 놓도록 안내한다. 헌법은 미작성 템플릿이며 설계 전후 한글 문서·speckit 절차를 준수한다.

## 모듈 파일명 변경 계획

src/pipeworks/embedded/tensor_rt_pre_process.py를 tensor_rt_pre_process.py로 이동한다. embedded/__init__.py·단일 예제·좌표 변환 테스트·최적화 테스트·benchmark_preprocess.py의 import와 patch 경로를 바꾼다. 벤치마크의 HEAD 원본 조회는 새 경로를 우선하고 해당 리비전에 없으면 옛 경로를 사용한다. 현재 계약의 소스 경로를 갱신한다. 새 의존성·처리 동작 변경은 없으며 기존 검증을 사용한다. 헌법은 미작성 템플릿이고 한글 문서·speckit 절차를 준수한다.

## 좌표 복원 객체 후속 계획 (2026-10-11)

이 계획이 기존의 호출자 직접 복원 책임을 대체한다. Python 3.11.9와 기존 PyTorch만 사용한다. src/pipeworks/image_transform.py에 불변 ImageTransform을 정의하고 기존 정보 속성을 유지한다. restore_boxes_는 xyxy의 축별 뷰에 이동량 제거·배율 나누기·경계 제한을 수행한다. CPU 복사·추가 동기화·프레임 참조는 없다.

src/pipeworks/embedded/tensor_rt_pre_process.py는 이 객체를 생성한다. examples/step/tensor_rt_post_process.py의 _restore를 제거하고 메서드를 호출한다. 후처리는 shape와 restore_boxes_만 사용한다. tools/benchmark_postprocess.py도 새 객체를 사용한다.

tests/test_image_transform.py에서 세 모드·옵션·빈 결과·경계·추가 열·저장 공간을 검증하고 tests/test_tensor_rt_processing.py에서 대체 객체 위임을 확인한다. 기존 좌표 테스트를 갱신하고 전후처리·보고 회귀를 실행한다. 문서와 검증 기록을 갱신한다. 헌법은 미작성 템플릿이며 설계 전후 한글 문서·speckit 절차에 위반은 없다.


examples/step/tensor_rt_pre_process.py와 tensor_rt_post_process.py의 빈 파일을 구현한다. NV12 색 변환은 기존 local_yolo GPU 함수를 재사용하고 torch 보간·패딩으로 입력과 복원 정보를 만든다. 후처리는 Ultralytics NMS와 Boxes를 이용하여 BoxOverlay와 동일한 감지 계약을 제공한다. 결과는 GPU에 유지하고 원본 orig_img는 만들지 않는다. BoxOverlay는 Async 타임아웃으로 detections 속성이 없는 입력도 결과 누락으로 처리한다.

examples/01_single_stream_rtsp_style.py의 클래스명·plan 경로·불필요 batch 인자를 수정하고 examples/config/stream.yml에 두 단계 설정을 추가한다. tests/test_tensor_rt_processing.py는 실제 CUDA 합성 입력과 출력을 검증한다. test_box_overlay.py의 예제 순서 검증은 TensorRT 경로에 맞춘다. 실제 엔진 추론도 가능한 환경에서 검증한다. 헌법은 미작성 템플릿으로 원칙 검사를 생략한다.
## 스트림·버퍼 후속 계획

전처리·직접 추론·후처리는 cuda_stream을 사용한다. 공유 배치 작업자는 입력 준비 이벤트를 기다린다. 후처리 finally에서 완료 확인·임시 속성 및 지역 참조를 정리하며 cuda_stream은 보존한다.

## 범용 내장 전처리 구현 계획

Python 3.11.9와 기존 PyTorch 2.2.1 CUDA 연산을 사용하고 새 의존성을 추가하지 않는다. 헌장은 미작성 템플릿이므로 원칙 검사를 생략한다. 한글 문서·순차 speckit 절차를 준수하며 별도 연구가 필요한 미확정 사항은 없다.

src/pipeworks/embedded/tensor_rt_pre_process.py에 옵션 검증·생성자 기본값·GPU 색상 변환·크기 변환·정규화·출력 구성을 구현한다. 기존 NV12 변환을 src/pipeworks/image.py로 분리하고 local_yolo.py는 같은 함수를 기존 이름으로 가져와 YOLO와의 수치 계약을 보존한다. RGB/BGR HWC 입력은 FP32 CHW의 독립 저장 공간으로 변환한다. 모델 라이브러리를 가져오지 않는다.

모든 설정은 구성 검증을 마친 뒤 한 번에 적용한다. _set_config_defaults와 _resolve_config로 기존 설정 우선순위를 유지한다. letterbox는 round와 bilinear 보간·stride 나머지 패딩, stretch는 독립 가로·세로 배율, 중앙 자르기는 size를 채우는 배율과 음수 이동량을 사용한다. 연산은 FP32로 수행하고 마지막에 FP16/FP32 및 NCHW/NHWC를 연속 저장 공간으로 반환한다. 채널별 패딩은 새 GPU 버퍼를 채우고 리사이즈 결과를 복사한다.

별도 모델 스트림과 영상 준비 이벤트를 유지하고 독립 영상 변환 후 release_frame 이벤트를 보낸다. tensor_rt_transform은 기존 shape·ratio·left·top에 ratio_xy·output_shape·resize_mode를 추가한다. 기본 letterbox의 기존 후처리 계약은 유지하고 임의 설정에 맞는 후처리는 호출자의 책임이다.

embedded/__init__.py에서 내보내고 examples/step/tensor_rt_pre_process.py는 호환용 재수출만 남긴다. 단일 예제는 embedded에서 가져오며 examples/config/stream.yml에 기본 설정을 명시한다. README.md와 docs/pipeworks/embedded/tensor_rt_preprocess.md에 전체 옵션·탐지 및 분류 예제·입력 형식·수치 한계를 안내한다.

tests/test_tensor_rt_preprocess.py는 구성·YAML 우선순위·잘못된 입력 및 실제 CUDA 수치·스트림·수명·출력 사전을 검증한다. tests/test_tensor_rt_processing.py와 관련 Async·보고·프레임 수명·YOLO 검증을 실행한다. 환경의 기존 전체 실패는 구분해 기록하고 이번 변경으로 발생하는 실패를 해결한다.

## 전체 YAML 옵션 노출 계획

examples/config/stream.yml에 누락된 stride, scaleup, center, padding_value, crop_size, mean, std, input_name을 기본값으로 추가한다. 의미가 헷갈릴 수 있는 모드·최소 패딩·자르기·정규화·입력 이름은 짧은 한글 주석으로 안내한다. 기존 나머지 옵션 값은 유지한다. YAML을 읽어 생성자 시그니처의 키 전체와 대조하고 configure 결과가 기본 생성자와 같은지 검증한다. 동작 변경이 없으므로 새 테스트 파일이나 GPU 전체 검증은 추가하지 않는다.

## 수정 설계: cuda_stream 통일

Python 3.11.9와 기존 CUDA·unittest를 사용한다. 별도 의존성은 추가하지 않으며 헌장은 미작성 템플릿이다. 전처리의 장치별 모델 스트림 캐시와 current_model_stream 참조·생산 이벤트 대기를 제거하고 item.cuda_stream 또는 현재 스트림을 사용한다. 추론은 입력 준비 이벤트를 같은 생산 스트림에 기록하고 개별 실행 스트림을 입력마다 선택한다. 공유 작업자 내부 스트림은 유지한다. 후처리는 입력 cuda_stream에서 실행하며 이 속성을 정리하지 않는다. CudaAsync 범위의 모델 스트림을 덮어쓰거나 일반 기능을 바꾸지 않는다.

tests/test_tensor_rt_preprocess.py·test_tensor_rt_processing.py·test_tensor_rt_model_ids.py·test_tensor_rt_inference.py의 스트림 계약을 검증하고 test_local_tensor_rt.py·test_frame_release.py·test_async.py·최적화 회귀를 실행한다. docs/pipeworks/embedded/와 docs/reference/reference.js의 설명을 갱신한다.

## 원격 실행 테스트 구성 보완 계획

 tests/test_async.py의 두 원격 실행 테스트에만 SimpleNamespace(development=False)를 추가한다. 실행 코드와 기존 직렬화 검증은 유지한다. 해당 테스트 두 개를 먼저 실행하고 test_async.py 전체와 공백 검사를 수행한다.
