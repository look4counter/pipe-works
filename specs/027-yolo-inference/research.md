# 조사 결과

## 원시 모델 실행

- 결정: 라이브러리 중립 실행 인터페이스와 명시적 호환 실행부를 사용한다.
- 근거: 로컬 AutoBackend의 CPU 전환 위험을 확인했으며 기본 TorchScript와 CUDA 직접 실행으로 대체한다.
- 대안: YoloDetect 상속과 predict는 전처리·NMS를 포함하므로 제외한다.

## 출력과 배치

- 결정: 주 예측과 모든 중첩 보조 텐서를 경로 이름으로 전달한다.
- 근거: TensorRTPostProcess가 output0을 소비한다. 기존 기본 전처리는 RGB FP32 NCHW이며 후처리는 COCO YOLO11 (1,84,N)을 가정한다. 다른 모델은 전후처리 수정이 필요하다.
- 대안: Results 반환은 원시 예측 계약에 맞지 않는다.
- 결정: 기존 수집기와 경로 캐시를 재사용하되 독립 워커를 둔다.
- 근거: 기존 local_yolo는 RGB 준비·감지까지 포함하므로 원시 입력을 처리할 수 없다.

## 불명확한 사항

기존 구조와 설치된 API로 모두 결정했다. 새 의존성이나 외부 조사가 필요하지 않다.

## 추가 조사: YOLO 전후처리

- 결정: 사용자 상속 변경 요청에 따라 YoloPreProcess는 Step을 직접 상속하고 GPU 변환 도우미를 자체 구현한다.
- 근거: 기존 TensorRT 전처리 모듈 의존성을 제거하며 검증된 색 변환·크기 변경·정규화·ImageTransform·release_frame 동작은 유지한다. nv12_to_rgb와 ImageTransform은 공용 모듈에서 재사용한다.
- 대안: TensorRTPreProcess 상속은 사용자 요청에 맞지 않으므로 제거한다. 별도 공통 기반 클래스 추출은 이번 요청보다 변경 범위가 넓어 적용하지 않는다.
- 결정: 설치된 Ultralytics non_max_suppression으로 FP32 감지 출력을 처리하며 사용자 클래스 names와 end2end를 지원한다.
- 근거: 로컬 nms.py에서 nc/end2end/classes/max_det 인자와 GPU torchvision NMS를 확인했다. 표준 출력 후보가 6개인 경우의 자동 end2end 분기는 마스킹된 추가 후보로 우회한다.
- 결정: _inference_profile을 세 단계가 공유하고 실제 추론 백엔드 kind/stats를 바인딩한 뒤 마지막 단계에서 한 번 종료한다.
- 근거: 두 보고 구현은 같은 표본/프로파일 인터페이스를 제공하지만 ContextVar와 저장소가 다르므로 kind와 stats 모두 재바인딩해야 한다.

## 공통 계약 조사

- 결정: backend 중립 모듈에서 GPU 전처리와 감지 후처리 구현을 공유하고 두 예제는 Step 직접 상속을 유지한다.
- 근거: 동일 GPU 연산·설정·변환 메타데이터를 이중 유지하지 않아도 되며 사용자가 요청한 TensorRT 예제 의존성 제거도 유지된다.
- 결정: TensorRT의 최적화된 여섯 열 후보 선택/NMS를 공통화하고 FP16·names·명시적 end2end를 확장한다.
- 근거: 읽기 전용 연구 에이전트가 기존 clone/CPU 복사 금지·좌표 제자리 변환 및 count=6 참조 테스트의 자동 end2end 분기 위험을 확인했다. raw 6 후보 참조는 비활성 후보를 하나 덧붙여 정확히 검증한다.
- 결정: CudaAsync 상태는 실제 inference 클래스가 있으면 그것을 우선한다.
- 근거: 전후처리 이름으로 분류하면 교차 연결에서 busy/timeout을 두 백엔드에 중복 기록하게 된다.

## GPU 전용 실행 조사: 2026-10-13

- 결정: AutoBackend를 제거하고 기본 TorchScript·명시적 Ultralytics 어댑터·사용자 실행부 인터페이스로 분리한다.
- 근거: 설치된 AutoBackend의 CPU 전환과 ONNX CPU provider 및 NumPy 변환 경로는 출력 GPU 검사만으로 감지되지 않는다.
- 대안: AutoBackend 결과만 GPU 검사하는 방식은 CPU 실행을 숨기므로 제외했다. ONNX 실행부 신규 구현은 별도 GPU 바인딩 설계가 필요하여 이번 범위에 넣지 않는다.
- 결정: TorchDispatchMode로 텐서 연산의 GPU를 감시한다. 실제 TorchScript의 CPU 이동이 aten._to_copy로 감시되는 것을 로컬 GPU에서 확인했다.
- 결정: 중첩 사전·목록·튜플의 모든 텐서 leaf를 경로 이름으로 보존한다. 설치된 YOLO 출력은 주 예측과 boxes/scores/feats 보조 출력이고 분할 출력도 중첩되어 있다.
- 결정: 공유 배치에서 모든 입력과 출력의 첫 축을 검증하고 실행부별 작업자 캐시를 분리한다. 스칼라 출력은 개별 실행에서만 가능하다.

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

## 공유 배치 통합 결정

- 결정: 하나의 수집 루프와 워커 캐시를 두고 원시 backend와 감지 세션의 실행 계약을 구분한다.
- 이유: 감지는 Results와 원본 좌표를 제공하고 원시 실행은 이름별 텐서를 제공하므로 결과 형식을 강제로 바꾸면 기존 단계가 깨진다. 큐·대기·오류 처리는 동일하여 공통화한다.
- 대안: 세 파일을 단순 연결하면서 별도 워커를 유지하는 방안은 중복 실행 관리가 남아 채택하지 않는다. 감지를 원시 추론으로 전면 교체하는 방안은 engine의 기존 Ultralytics 자동 해석까지 바꾸므로 이번 내부 통합에서는 기존 세션 동작을 보존한다.

## 예제 전후처리 경계 결정

- 결정: 전후처리를 YOLO 예제 두 파일이 소유하고 기존 TensorRT 예제는 메서드 재사용으로 유지한다.
- 이유: 실행 backend는 이미지 포맷이나 NMS를 알 필요가 없고 동일한 출력 계약이면 후처리를 공유할 수 있다.
- 대안: 코어에 호환 이미지 변환을 남기거나 YoloDetect를 예제로 옮기는 방안은 사용자의 명시적 삭제 지시로 제외했다. 예제에서 코어 유틸을 다시 가져오는 구조도 제외한다.
