# 데이터 모델

## 컨텍스트

- model_input: 지정 GPU의 텐서 또는 이름별 텐서 사전. 입력 각 축은 양수이며 구체적인 형상·자료형은 실행부가 검증한다.
- cuda_stream: 입력 생산 스트림. 없으면 지정 GPU의 현재 스트림을 설정한다.
- model_id: 설정 식별자. 생략/null이면 확장자를 포함한 파일명이다.
- model_output: 성공 시 이름별 모든 원시 GPU 출력 사전, 건너뜀·실패 시 None.
- frame/detections: 추론 단계는 읽거나 변경하지 않는다.

## 공유 요청

입력, GPU, 호환 키, 준비 이벤트, 수신 시각, 완료 신호, 결과, 오류, 추론 시간, 선택적 보고 정보를 가진다. 요청당 B=1이다.

## 상태 전이

대기 → 호환 배치 수집 → 이벤트 대기 → 입력 결합 → 모델 실행 → 결과 복제 → GPU 완료 → 요청 완료. 실패도 GPU를 정리하고 모든 대기자를 깨운다.

## YOLO 전후처리 상태

- image_transform: ImageTransform 또는 shape/restore_boxes_ 인터페이스를 구현한 객체. 원본 크기, x/y 비율, 왼쪽/위 패딩, 출력 크기를 보관한다.
- _inference_profile: 선택적 공통 프로파일. 전처리가 시작하고 추론이 실제 백엔드 kind/stats를 바인딩하며 후처리가 종료한다.
- detections: 모델 ID별 사전. 해당 ID에 None 또는 GPU boxes·names·orig_shape 결과를 기록하고 다른 ID는 보존한다.
- names: 0부터 연속하는 정수 ID와 비어 있지 않은 이름의 사전. 목록도 설정에서 이 사전으로 변환한다.

전처리 완료 → 추론 완료 또는 건너뜀 → 후처리 결과 저장·임시 상태 정리·프로파일 완료 순서다. 실패는 프로파일 오류 상태이고 비동기 중도 종료는 부분 종료 상태다.

이전 yolo_transform/tensor_rt_transform 및 _yolo_profile/_tensor_rt_profile은 공통 필드가 없을 때 입력 호환으로 읽는다. 새 전처리는 이전 필드를 생성하지 않는다. 정리 시에는 모두 제거한다.

model_input은 단일 GPU 텐서 또는 이름별 GPU 텐서 사전이다. YOLO는 선택 실행부가 지원하는 이름별 다중 입력을 받을 수 있고 TensorRT는 실제 엔진 선언의 모든 입력을 받을 수 있다. 출력 사전 키는 모델의 출력 계약이며 YOLO 주 예측은 output0이다.

## GPU 실행부와 입출력

- 실행부 선택자: 기본 torchscript, 명시적 ultralytics 또는 모듈:클래스. 생성자 및 단계 YAML에서 지정한다.
- 모델 입력: GPU 텐서 또는 비어 있지 않은 문자열 키의 GPU 텐서 사전. 차원과 자료형은 모델 계약에 따른다. 공유 요청은 각 입력의 첫 축이 1이다.
- 모델 출력: 실제 사전 키나 결정적인 중첩 경로를 키로 하는 독립적인 GPU 텐서 사전. 빈 텐서는 허용하며 빈 컨테이너·비텐서 leaf는 오류다.
- 실행 세션: 모델 경로·GPU·실행부를 기준으로 로드한다. 실행 중 GPU 계약 오류는 호출자에게 전파하며 GPU를 정리한다.
- 공유 요청 서명: 실행부·GPU·입력 이름별 자료형과 비배치 형상. 모든 출력 첫 축은 결합 요청 수와 같아야 한다.

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

## 통합 공유 요청

원시 요청은 backend, GPU, profile_index, 입력 서명, 완료 신호, GPU 출력 사전을 가진다. 감지 요청은 GPU 이미지와 필터 옵션, 감지 Results 및 GPU 완료 이벤트를 가진다. 두 요청은 같은 워커 수집·완료 수명주기를 사용하되 서로 다른 실행 종류로 격리한다. 세션은 워커 안에서 GPU·profile별로 재사용하며 실패 후 해당 세션만 닫고 제거한다.

## 예제 소유 이미지 정보

ImageTransform은 yolo_pre_process의 불변 객체로 원본 shape, ratio_xy, left/top, output_shape, resize_mode를 유지한다. 후처리는 restore_boxes_와 shape 계약으로만 접근한다. 코어 요청은 GPU 텐서·backend·profile·완료 신호와 원시 출력 사전만 가진다. 감지 전용 요청 개체는 삭제한다.
