# 공개 계약: YoloInference

생성자는 YoloInference(model_path, *, batch=False, gpu_id=0, inference_interval_frame=1, id=None, backend="torchscript")이다. batch는 불리언이며 YAML 대상이 아니다. GPU는 음수가 아닌 정수, 간격은 1 이상의 정수, ID는 비어 있지 않은 문자열 또는 None이다. YAML의 YoloInference 섹션이 기본값을 덮어쓰며 키 제거는 생성자 값으로 돌아간다.

YOLO 입력은 지정 GPU의 텐서 또는 이름별 다중 입력 사전이다. 구체적인 형상·자료형은 실행부가 검증한다. 전처리가 크기·정규화를 맞춘다. 공유 배치는 B=1만 허용한다. 모든 중첩 원시 출력을 model_output의 실제 이름 또는 결정적인 경로 이름으로 전달한다. NMS와 좌표 복원은 후처리 책임이다.

개별 추론은 전체 B를 실행한다. 공유 배치는 경로·실행부·GPU·입력 이름·자료형·형상이 호환되는 요청을 결합하고 요청별 복사본을 반환한다. 인접 YAML의 max_batch_size/timeout_ms는 기존 YOLO 규칙을 따른다.

항상 model_id와 초기화된 model_output을 기록한다. 건너뜀은 입력 검증과 모델 준비를 하지 않는다. 오류는 직접 호출자에게 전달하며 CudaAsync에서는 기존 오류·타임아웃 처리를 따른다.

## YOLO 예제 전후처리

YoloPreProcess는 Step을 직접 상속하며 TensorRTPreProcess 및 해당 예제 모듈을 가져오지 않는다. 두 전처리는 백엔드 중립 GPU 도우미로 같은 변환·설정 검증을 제공한다.

두 PreProcess는 기본 640×640 letterbox, padding_value=114, scale=1/255, RGB NCHW FP32 배치 1을 제공한다. 크기 변경·정규화·color_order·dtype·layout·input_name 옵션이 같다. 실제 추론 모델에 맞는 옵션을 선택한다. image_transform과 선택적 _inference_profile을 설정한다.

step.yolo_post_process.YoloPostProcess는 confidence=0.25, iou=0.7, classes=None, max_det=300, output_name='output0', names=None, end2end=False를 키워드 생성자로 받는다. names=None은 COCO 이름이고 사용자 이름 목록 또는 연속 정수 키 사전을 지정할 수 있다. FP32/FP16 배치 1 감지 예측을 검증한 뒤 FP32 GPU NMS와 좌표 복원을 수행한다. end2end=True는 이미 NMS를 포함한 (1,N,6) 출력이다.

각 예제 클래스명 YAML 섹션이 생성자 값을 덮어쓴다. 두 PostProcess는 같은 생성자·기본값을 제공한다. TensorRTPostProcess의 기존 classes=[2] 기본값은 None으로 통일한다. 후처리는 detections[model_id]만 갱신하고 임시 상태를 정리한다. 전체 연결은 실제 추론 백엔드의 프로파일 한 개가 전처리·추론·후처리를 포함한다. 추론만 사용하면 기존 자체 보고 동작을 유지한다.

공통 좌표 정보는 image_transform이다. 이전 변환/프로파일 필드는 입력 호환용으로 읽지만 새 전처리는 공통 필드만 생성하며 후처리는 공통·이전 임시 필드를 모두 제거한다.

## GPU 전용 실행부 계약: 2026-10-13

- backend는 torchscript(명시적 선택), ultralytics(명시적 호환), 모듈:클래스 중 하나다. 사용자 클래스는 생성자에 model_path와 gpu_id를 받고 infer(inputs)를 제공한다.
- 입력은 지정 GPU의 연속 텐서 또는 이름별 텐서 사전이며 공통 계층에서 채널·자료형·순위를 모델별 값으로 제한하지 않는다. 단일 요청의 입력 크기 각 축은 양수다.
- 출력은 GPU 텐서, 사전, 목록, 튜플을 중첩할 수 있다. 사전의 실제 키는 보존한다. 텐서는 output0, 시퀀스 항목은 output번호, 중첩 항목은 / 경로를 쓴다. 빈 컨테이너·비텐서·중복 경로는 명확한 오류다.
- CPU·다른 GPU 텐서와 추론 중 장치 전환은 거부한다. 데이터의 CPU 복사와 자동 CPU 실행을 제공하지 않는다. 제어·모델 역직렬화는 CPU에서 가능하며 사용자 네이티브 실행부도 동일 계약을 지켜야 한다.
- 공유 실행에서는 이름·자료형·비배치 형상이 같은 요청만 결합한다. 모든 입력 첫 축은 1, 모든 출력 첫 축은 결합 배치 크기이며 스칼라 출력은 공유 실행에서 거부한다.
- 기존 Ultralytics 체크포인트는 backend=ultralytics로 명시한다. 주 감지 출력의 output0은 유지하되 보조 텐서를 삭제하지 않는다. 분할·포즈 해석은 사용자 후처리에 위임한다.

## Backend 필수 선택

Backend.TORCHSCRIPT, Backend.ULTRALYTICS와 Backend.TENSORRT를 공개한다. YoloInference의 backend는 필수 키워드이며 사용자 정의 모듈:클래스 문자열과 YAML 문자열을 유지한다. YAML 내장 값은 enum으로 정규화하고 설정 제거 시 생성자 선택으로 복원한다. 공개 가져오기·생략 오류·설정 복원과 기존 추론 회귀로 검증한다.


## TensorRT 통합 계약

Backend.TENSORRT의 값은 tensorrt이다. YoloInference는 profile_index=0을 기본으로 받고 TensorRT 최적화 프로파일을 선택한다. 다른 실행부의 0 이외 프로파일은 거부한다. 기존 GPU 입력/이름별 출력과 동적 형상·플러그인·공유 배치 동작을 유지한다. YoloReport와 CudaAsync는 실제 backend를 기준으로 기록한다. 이전 TensorRTInference 호환 래퍼는 제거한다.


## 이전 클래스 제거

TensorRTInference 호환 래퍼와 모듈·공개 export는 제거한다. TensorRT 엔진은 YoloInference(..., backend=Backend.TENSORRT)로 실행하고 YAML은 YoloInference 섹션을 사용한다. 내부 도우미는 yolo_backends.tensorrt에서 가져오며 보고는 YoloReport로 통합한다. 제거 확인과 기존 GPU·설정·보고 계약을 검증한다.


## 공통 보고 계약

TensorRTReport와 별도 저장소를 제거하고 YoloReport에서 모든 실행부를 활성화한다. 프로파일과 표본은 하나의 실행 범위 저장소를 공유하며 YOLO, ULTRALYTICS, TORCHSCRIPT, TensorRT 및 사용자 경로별로 구분한다. 전후처리의 프로파일은 실제 추론 종류로 연결하고 종료 상태를 한 번만 기록한다. 비활성 이벤트·공유 배치 범위·GPU 처리 계약은 유지한다.

## 통합 보고 명칭

공개 클래스는 YoloReport이고 구현 모듈은 pipeworks.embedded.yolo_report이다. 이전 클래스와 모듈 별칭은 제공하지 않는다. 기존 공통 보고 수집·출력 계약은 유지한다.

## 중앙 배치 검증 계약

세 backend를 실제 중앙 프로세스에서 실행하고 두 파이프라인의 요청을 두 라운드 동안 배치 2로 묶는다. 실제 모델 forward의 PID·워커 스레드·세션 ID·입력 GPU를 관찰한다. 결과는 요청별 독립 GPU 배치 1이며 개별 참조와 일치한다. 중앙 프로세스에서 입력을 생성하고 CudaAsync·YoloReport 경로 및 실행 범위별 완료 2개를 확인한다. 테스트 전용 그룹과 로컬 생성 모델을 사용한다.

## 공유 실행 통합

공유 원시 추론은 local_yolo_inference.infer의 backend와 TensorRT 전용 profile_index를 사용한다. 감지는 같은 모듈의 infer_detection이 기존 이미지·필터·GPU Results 계약을 제공한다. local_yolo와 local_tensor_rt 모듈은 제거하며 호환 모듈은 남기지 않는다. 공개 YoloInference와 YoloDetect 생성자·결과 계약은 유지한다.

## 전후처리 예제 경계

YoloPreProcess와 YoloPostProcess는 examples/step에서 직접 구현한다. ImageTransform과 nv12_to_rgb는 step.yolo_pre_process에서 가져온다. TensorRTPreProcess/TensorRTPostProcess는 기존 예제 이름을 유지하며 같은 메서드를 재사용한다. YoloDetect 및 infer_detection과 네 코어 이미지 모듈은 제거한다. 기존 감지 파이프라인은 전처리 → 필수 backend를 지정한 YoloInference → 후처리 조합으로 이관한다.
