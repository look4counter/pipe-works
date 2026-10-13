# 구현 계획: YOLO 추론 단계 분리

**기능**: 027-yolo-inference | **날짜**: 2026-10-12 | **명세**: [spec.md](spec.md)

## 요약

YoloDetect를 수정하지 않고 YoloInference와 원시 추론용 공유 작업자를 추가한다. TensorRT의 model_input/model_output/model_id 계약으로 전후처리를 분리한다.

## 기술 맥락

- 언어: Python 3.11.9
- 의존성: 기존 torch 2.2.1+cu121, PyYAML. ultralytics 8.4.146은 명시적 호환 실행부에만 사용
- 저장: 기존 모델 파일과 인접 모델 YAML
- 검증: unittest CPU 모의 검증 및 CUDA 사용 가능 시 GPU 검증
- 플랫폼: NVIDIA CUDA 기반 SDK
- 성능: 기존 배치 수집기를 사용하고 CPU 텐서 이동을 추가하지 않는다.
- 제약: frame/detections는 읽거나 변경하지 않는다. 입력은 GPU 텐서 또는 이름별 GPU 텐서 사전이다. 모델 실행부가 구체적인 형상·자료형을 검증한다.
- 범위: 추론 단계, 공유 워커, 내보내기, 비동기 보고 인식, 문서와 계약 테스트

## 헌장 확인

헌장은 미작성 템플릿으로 규범 검사를 생략한다. AGENTS.md의 한글 문서와 전체 speckit 절차를 적용한다. 설계 전후 위반이 없다.

## 조사와 설계

- 라이브러리 중립 실행부 인터페이스를 사용한다. 기본은 TorchScript이며 Ultralytics는 명시적인 체크포인트 호환 실행부에 격리한다. AutoBackend와 predict는 사용하지 않는다.
- 모든 중첩 출력 텐서를 사전 키 또는 경로 이름으로 보존한다. GPU를 검증하고 공유 배치에서만 출력 배치 축을 요구한다.
- 개별 모델은 생성기 안에서 GPU·실행부별로 재사용한다. 생산 스트림 준비 이벤트를 기다린다. 비연속 입력의 GPU 연속화만 수행한다.
- 공유 워커는 collect_batch/get_model_worker/기존 YOLO 배치 YAML 검증을 재사용하되 별도 저장소를 둔다. 호환 키는 실행부·GPU·입력 이름·자료형·비배치 형상이다.
- 출력은 요청별 clone으로 전달한다. 실패 시 모델 캐시 제거, GPU 정리, 모든 대기자 깨우기를 보장한다.
- YOLO 보고 begin/span/use와 StreamReport 추론 시간을 연결한다. CudaAsync에서 새 단계 이름을 인식한다.
- 설정·간격·오류·원시 출력·배치 분리·GPU 검증과 기존 회귀 테스트를 수행한다.

## 프로젝트 구조

- src/pipeworks/embedded/yolo_inference.py: 추론 단계와 원시 세션
- src/pipeworks/local_yolo_inference.py: 공유 배치 워커
- src/pipeworks/embedded/__init__.py: 공개 내보내기
- src/pipeworks/embedded/cuda_async.py: YOLO 보고 인식
- tests/test_yolo_inference.py: 신규 계약 검증
- docs/pipeworks/embedded/yolo_inference.md 및 README.md: 사용 안내
- specs/027-yolo-inference: 명세·계획·조사·데이터 모델·계약·검증 안내·작업 목록

## 추가 설계: YOLO 전후처리 예제

- examples/step/yolo_pre_process.py의 YoloPreProcess는 Step을 직접 상속한다. 백엔드 중립 공통 GPU 전처리 도우미를 사용하며 TensorRT 전처리 예제 모듈에 의존하지 않는다. 기본 출력은 RGB NCHW이고 모델별 옵션은 두 전처리가 동일하게 제공한다.
- examples/step/yolo_post_process.py의 YoloPostProcess는 독립 Step이다. 기본 COCO 이름과 모든 클래스, confidence=0.25, iou=0.7, max_det=300, output_name=output0을 사용한다. 사용자 names와 이미 NMS를 포함한 end2end 형식을 명시적으로 설정할 수 있다. GPU FP16은 FP32로 바꾼 뒤 NMS한다.
- 표준 원시 출력은 (1,4+클래스수,N)이고 end2end는 (1,N,6)이다. 표준 출력은 여섯 열 후보 선택과 GPU torchvision NMS를 사용하고 end2end는 Ultralytics 필터를 사용한다. 표준 후보 수 6은 end2end로 자동 해석하지 않는다. 참조 테스트에서는 비활성 후보 패딩으로 라이브러리 자동 분기를 피한다. 후보 0개도 빈 결과로 처리한다.
- 전처리는 image_transform과 _inference_profile을 생성한다. 추론은 상속 프로파일을 실제 백엔드에 바인딩하고 완료를 후처리에 위임하며 단독 사용은 기존 동작을 유지한다. 상속 프로파일이 있는 건너뜀은 후처리가 상태를 기록한다.
- 후처리는 detections 사전을 복제하여 다른 모델 결과를 보존한다. 건너뜀과 오류를 포함한 모든 종료에서 model_input/model_output/image_transform/model_id/_inference_profile 및 이전 임시 필드를 정리한다.
- CudaAsync는 YOLO 전후처리 클래스와 상속 프로파일도 인식하고 부분 종료를 기록한다. 프레임 해제와 비동기 원본 보존 계약은 기존과 같다.
- examples/01_single_stream_rtsp_style.py에 사용자가 연결한 새 단계의 import를 추가하고 YoloReport로 연결한다. 나머지 사용자 변경은 보존한다.
- tests/test_yolo_processing.py에서 GPU 색 변환·letterbox·FP16·NMS·사용자 클래스·빈 결과·건너뜀·오류 정리·전체 보고·비동기 처리를 검증한다. 기존 추론 및 TensorRT 전후처리 회귀 검증을 실행한다.
- docs/pipeworks/embedded/yolo_inference.md와 README.md 및 빠른 검증 안내에 YOLO 전후처리 연결을 기록한다.

추가 설계에서도 새로운 의존성이나 헌장 위반은 없다.

## 상속 변경 설계

- Step 직접 상속 변경은 완료했다. 추가 공통 계약 요청에서는 두 전후처리 예제와 두 추론 단계의 연결 코드를 함께 갱신한다.
- GPU 도우미의 자체 구현을 거쳐 공통 계약 요청에 따라 백엔드 중립 도우미로 공유한다. nv12_to_rgb와 ImageTransform은 기존 공용 모듈에서 가져온다.
- 기본 RGB NCHW 출력, 캐시 재설정, 원본 독립 저장소, 프레임 해제 이벤트를 유지하며 color_order/layout/input_name은 두 전처리에서 공통 옵션으로 제공한다.
- TensorRT 전처리 모듈 가져오기를 차단하여 독립성 계약을 검증하고 기존 YOLO 처리·추론 테스트를 실행한다.
- 미확정 기술 선택과 추가 의존성은 없다. 명세 품질 체크리스트 16개가 계속 충족되며 설계 전후 헌장 위반이 없다.

## 공통 계약 설계

- src/pipeworks/inference_contract.py: image_transform 조회, 임시 정리, 공통 프로파일 생성/백엔드 바인딩/종료 조회. 새 필드는 image_transform과 _inference_profile이며 이전 두 계열 필드는 읽기 fallback 및 정리 대상으로 유지한다.
- src/pipeworks/image_preprocessing.py: 기존 검증된 GPU 변환 도우미와 process를 공통 함수로 옮긴다. 두 PreProcess는 Step을 직접 상속하고 동일 생성자·설정·메서드로 이 함수를 사용한다. 별도 기능 기반 클래스 상속은 도입하지 않는다.
- src/pipeworks/detection_postprocessing.py: 사용자 names·FP16·end2end 지원을 공통화하면서 기존 TensorRT의 여섯 열 후보 선택/NMS 최적화를 유지한다. 표준 (1,4+nc,N)과 명시적 end2end (1,N,6)를 구분한다. 두 PostProcess 생성자와 기본값은 동일하고 classes=None이다.
- 전처리는 활성 보고가 있으면 공통 프로파일을 생성한다. 추론은 실제 YOLO/TensorRT kind와 stats로 바인딩하고 자신의 span 컨텍스트에 사용한다. 후처리는 상속된 프로파일을 종료한다. 두 보고 구현의 표본/프로파일 인터페이스가 같으므로 기존 보고 클래스를 유지한다.
- YoloInference는 이름별 GPU 다중 입력을 유지하여 모델 실행부와 개별·공유 실행에 전달한다. 단일 입력만 지원하는 호환 실행부는 명확한 오류로 다중 입력을 거부한다. TensorRT의 실제 입력/출력 이름과 profile_index는 유지한다.
- CudaAsync는 공통 프로파일을 포함해 미종료 작업을 정리하고 추론 클래스가 있으면 그 kind로 timeout/busy를 분류한다. 추론이 없는 전후처리 묶음은 예제 계열을 기본 보고 kind로 사용한다.
- tests/test_inference_contract.py: 모든 교차 전후처리 조합, named input, FP16/사용자 클래스, cleanup, 백엔드별 단일 보고, 비동기 부분 종료 검증. 실제 YOLO 모델과 기존 TensorRT 엔진도 교차 연결한다.
- 기존 테스트와 문서의 공개 변환 필드는 image_transform으로 갱신한다. 기존 차량 필터를 의도한 검증은 classes=[2]를 명시하고 기본값 검증은 None으로 바꾼다. 기존 이전필드 입력 호환은 별도 검증한다.
- 문서에서 같은 전후처리와 추론 교체 예제, 기본 차량 필터 변경, 모델별 실제 형상/자료형/이름 제약을 안내한다.

새 의존성이나 헌장 위반은 없다. 구현 전 분석에서 공통화 작업과 기존 완료 작업의 모순을 제거한다.

## 실행 단계

명세·명확화 → 조사·설계 → 작업 생성 → 읽기 전용 분석 → 계약 테스트와 구현 → 회귀 검증 → 수렴 검토 순서로 진행한다.

## GPU 전용 범용 실행 설계: 2026-10-13

- src/pipeworks/yolo_backend.py: 실행부 프로토콜, 지연 로딩 선택자, 입력·중첩 출력 GPU 검증, CPU 전환을 거부하는 TorchDispatchMode, 텐서 입력 서명과 배치 설정을 제공한다. 선택자는 torchscript(명시적 선택), ultralytics(호환), 또는 모듈:클래스 문자열이다.
- src/pipeworks/yolo_backends/torchscript.py: torch.jit.load(map_location=cuda)와 eval()을 사용하며 입력 사전은 모델의 이름 있는 인자로 전달한다. 모델 파라미터와 버퍼는 지정 GPU인지 확인한다.
- src/pipeworks/yolo_backends/ultralytics.py: load_checkpoint(device=cuda)로 PyTorch 모델을 로드하고 직접 실행한다. FP32/FP16 단일 이미지 입력은 이 어댑터에만 제한한다. AutoBackend의 CPU 선택과 NumPy 변환을 제거한다.
- 공통 실행부 생성자는 model_path와 gpu_id를 받고 infer(inputs)로 GPU 텐서 또는 이름별 사전을 실행한다. 출력은 GPU 텐서·중첩 사전·목록·튜플이다. 이름 없는 단일 텐서는 output0, 목록은 output0/output1, 중첩은 / 경로로 평탄화하며 사전 이름은 보존한다. 비텐서·빈 컨테이너·이름 충돌은 거부한다.
- 모든 실행은 TorchDispatchMode 안에서 지정 GPU 입력·출력·요청 장치를 검증한다. CPU 텐서와 CPU 전환을 거부하고 실제 TorchScript CPU 전환 모델로 확인한다. 외부 네이티브 코드 내부는 커스텀 실행부의 GPU 계약 책임이다. 모델 로딩과 파일 I/O는 감시 범위 밖이다.
- YoloInference에는 backend 생성자/YAML 옵션을 추가한다. 공통 입력의 3채널·4차원·부동소수점 고정을 제거하고 다중 입력을 그대로 전달한다. 동적 YAML 실행부 변경 시 세션을 다시 로드한다.
- 공유 실행은 실행부별 경로 캐시를 분리하고 입력별 GPU·자료형·형상·이름 서명으로 결합한다. 입력별 torch.cat으로 배치하고 출력별 첫 축을 검증하여 독립적으로 분리한다. 실패 시 관련 요청을 모두 깨운다.
- examples/config/stream.yml의 YoloInference는 기존 yolo11n.pt를 위해 backend: ultralytics를 명시한다. 의미 없는 profile_index는 제거한다. 현재 영상·모델·사용자 클래스 설정을 보존한다.
- tests/test_yolo_gpu_backends.py에 실제 GPU 라이브러리 차단, TorchScript 다중 입출력·보조 출력, CPU 전환 감시, 공유 출력 분리·배치 축 오류·실행부 격리 검증을 추가한다. 기존 추론·교차 계약·보고 테스트를 새 계약에 맞게 갱신한다.
- 새 외부 의존성은 추가하지 않는다. 헌장은 미작성 템플릿이므로 규범 검사는 생략하며 AGENTS.md 한글 문서와 전 단계 절차를 유지한다.

## 필수 Backend 설계

Python 3.11 StrEnum을 src/pipeworks/backend.py에 정의하고 pipeworks 및 pipeworks.embedded에서 공개한다. 현재 실행부 TORCHSCRIPT, ULTRALYTICS, TENSORRT를 등록한다. 생성자는 backend: Backend | str을 필수 키워드로 받는다. 문자열은 기존 사용자 실행부 호환을 위해 유지한다. configure는 내장 문자열을 enum으로 정규화하고 사용자 경로는 기존 검증을 유지한다. 내부 StrEnum은 문자열과 동일하게 비교·해시되어 세션과 공유 워커를 변경하지 않는다.

기존 예제·테스트·문서 호출은 enum을 명시하며 YAML은 문자열을 유지한다. 추가 의존성은 없다. 헌장은 미작성 템플릿이며 한글 문서와 전체 워크플로우 절차를 준수한다. 계약 테스트 후 관련 회귀를 실행한다.


## TensorRT 통합 설계

TensorRT 엔진 도우미와 _EngineSession은 src/pipeworks/yolo_backends/tensorrt.py로 이동한다. 이 모듈은 TensorRT 런타임을 세션 생성 시 지연 가져온다. YoloInference에 기존 TensorRT 설정·실행 경로를 포함하고 backend에 따라 실행 경로를 선택한다. GPU 입력 계약과 모델별 출력은 기존과 같다. profile_index는 설정 검증 후 반영하고 TensorRT 이외에서 0만 허용한다.

src/pipeworks/embedded/tensor_rt_inference.py 호환 래퍼는 후속 제거 요구에 따라 삭제한다. 내부 엔진 도우미는 backend 모듈에서 직접 가져온다. local_tensor_rt는 엔진 backend 모듈에서 도우미를 가져오며 기존 검증된 배치 워커를 유지한다. 실행은 공통 추론 클래스가 위임한다. CudaAsync는 클래스 이름보다 backend 값을 우선하여 보고 kind를 선택한다. 기존 테스트 patch 경로를 새 실행 위치로 갱신한다.

examples와 YAML·README·공개 안내에 Backend.TENSORRT와 YoloInference 섹션을 사용한다. 이전 TensorRTInference YAML 섹션은 YoloInference로 이관한다. 추가 의존성 없음. 헌장은 미작성 템플릿이며 한글 문서와 전체 단계 절차를 준수한다. 통합 계약 테스트를 먼저 추가한 후 GPU·설정·배치·보고 회귀를 수행한다.


TensorRTBackend 어댑터는 공통 load_backend 선택자에서도 TensorRT 엔진을 로드하고 infer(inputs)를 제공한다. 엔진의 GPU 바인딩 검증을 사용하며 PyTorch의 GPU 출력 검증·복제를 유지한다. TensorRT 제어용 CPU 메타데이터 연산은 TorchDispatchMode 감시를 적용하지 않는다. 엔진 모듈의 보고 도우미는 실행 시 가져와 local_tensor_rt를 먼저 가져오는 경우에도 순환 의존성을 피한다.

## 호환 래퍼 제거 설계

src/pipeworks/embedded/tensor_rt_inference.py를 삭제하고 embedded/__init__.py의 가져오기·__all__ 항목을 제거한다. cuda_async의 이전 클래스 이름 분류를 제거한다. TensorRT 엔진 도우미는 기존 yolo_backends/tensorrt.py에서 유지하며 설정 오류 안내는 YoloInference 섹션을 가리킨다.

기존 테스트는 생성자에 backend=Backend.TENSORRT를 명시하고 간접 생성자 표는 backend enum으로 구분한다. _EngineSession은 backend 모듈에서 직접 가져온다. YAML은 YoloInference 섹션으로 변경한다. 제거 확인 테스트는 공개 export 부재와 importlib 모듈 탐색 실패를 확인한다.

문서의 TensorRT 호출과 설정을 통합 API로 갱신하고 docs/reference/TensorRTInference.html을 YoloInference.html로 대체한다. reference.js의 이름·입출력 안내와 설정 표에 backend 필수 선택을 반영한다. 보고는 YoloReport로 통합하며 TensorRT 엔진 상세 안내 파일은 엔진 계약 문서로 유지한다. 추가 의존성이 없고 헌장은 미작성 템플릿이다. 한글 문서와 전체 워크플로우 절차를 준수한다.


## YoloReport 통합 설계

embedded/yolo_report.py의 프로파일·통계·출력 구현을 모든 backend에서 공유한다. DetectionStats는 Report 전체 활성화를 지원하고 기록된 backend 목록을 반환한다. YoloReport는 실행 범위의 모든 backend를 활성화하고 기록된 종류별로 출력하며 종료 시 정리한다. YOLO 기존 감지와 ULTRALYTICS, TORCHSCRIPT, TensorRT를 분리한다.

YoloInference는 backend에 따른 report_kind를 제공한다. 공통 전후처리는 하나의 저장소에서 활성 프로파일을 준비하고 실제 추론이 종류를 확정한다. local_yolo_inference와 local_tensor_rt, TensorRT 엔진, CudaAsync는 공통 프로파일·상태 함수를 사용한다. stream_report.py의 별도 tensor_rt_detection_stats는 제거한다. tensor_rt_report.py와 공개 export를 삭제한다.

tests/test_detection_report.py에서 혼합 backend 활성화·분리 출력·공유 컨텍스트 중첩·삭제 부재를 검증하고 기존 GPU 계약 테스트를 새 종류에 맞춰 갱신한다. README·examples·docs는 공통 보고 연결만 안내한다. 추가 의존성 없음. 헌장은 미작성 템플릿이며 한글 문서·전체 단계 절차를 준수한다.

## YoloReport 이름 변경 설계

embedded/yolo_detect_report.py를 embedded/yolo_report.py로 옮기고 클래스·공개 export·ContextVar 이름 및 모든 가져오기·patch 경로를 갱신한다. inference_contract의 동적 모듈 경로와 TensorRT 엔진의 지연 가져오기도 새 모듈을 사용한다. 구현 논리는 바꾸지 않는다.

기존 보고 테스트의 새 공개 클래스 확인을 먼저 적용하여 이전 구현에서 실패를 확인한다. 그 뒤 기존 실제 GPU·배치·전후처리·비동기 회귀를 실행한다. README·docs·examples의 안내와 호출도 YoloReport로 갱신한다. 추가 의존성 없음. 헌장은 미작성 템플릿이며 한글 문서와 전체 단계 절차를 준수한다.

## 중앙 배치 검증 설계

tests/test_central_yolo_inference.py에 실제 중앙 프로세스 검증을 추가한다. Ultralytics는 설치된 YOLO11 설정에서 가중치를 생성하고 TorchScript는 작은 실제 GPU 모델, TensorRT는 배치 1~4 동적 프로파일이 있는 작은 실제 엔진을 생성한다. 모델별 max_batch_size=2와 수집 제한 시간을 설정한다.

두 Pipeline.run 호출을 테스트 전용 중앙 그룹의 실제 AF_PIPE 연결로 전달한다. 테스트에서 그룹 선택만 바꾸며 전송·직렬화·실행과 모델 forward는 실제 구현을 사용한다. GPU 입력은 중앙 Source에서 생성하여 프로세스 간 영상 텐서를 보내지 않는다. 두 Source는 라운드별 준비 파일로 동기화하고 개별 추론 참조는 별도 비활성 보고 범위에서 준비한다.

중앙 배치 워커의 실제 infer 호출을 감싸 PID·스레드·입력 배치 크기·GPU·세션 ID를 관찰하되 원래 추론은 그대로 실행한다. Sink는 모든 GPU 출력을 개별 참조와 비교하고 출력 복제의 독립성을 확인하며 작은 JSON 진단만 기록한다. CudaAsync와 YoloReport를 포함하여 각 파이프라인의 완료 2개와 배치 구간을 확인한다. 두 라운드에서 실제 배치 2와 세션 재사용을 검증한다.

새 외부 의존성과 운영 코드 변경은 계획하지 않는다. 테스트 실패 시 실제 원인에 한해 수정 범위를 추가한다. 기존 배치·보고 회귀를 함께 실행하며 세 backend가 모두 실제 실행되었는지 결과를 명시한다. 헌장은 미작성 템플릿이며 한글 문서와 전체 절차를 준수한다.

## 검증 환경 보완

Windows 가상환경 런처의 Popen PID와 실제 Python PID가 다를 수 있으므로 중앙 서버의 실제 ping 응답 PID와 워커·Source·Sink PID를 비교한다. Source와 Sink의 Hotswap은 검증 오류를 즉시 전달하도록 recover_errors=False로 설정한다.

TorchScript 검증 모델은 CPU 스칼라 읽기가 없는 실제 GPU neg·multiply 연산을 사용한다. 개별 참조는 같은 세션으로 두 라운드를 먼저 준비하여 실제 배치 실행 사이에 참조 모델 재로딩을 끼우지 않는다. YoloReport의 최근 10초 표본 창 안에서 두 배치 라운드를 검증한다. 테스트가 시작한 전용 서버만 종료하고 소유한 stderr 핸들도 정리한다. 운영 Batch 구현은 변경하지 않는다.

## 공유 배치 모듈 통합 설계

local_yolo_inference의 단일 _ModelWorker가 모든 요청을 수집한다. 원시 요청은 backend·GPU·profile_index·입력 서명으로, 감지 요청은 별도 내부 실행 종류·GPU·클래스·신뢰도로 묶는다. 캐시와 별칭 해석은 실행 종류별로 격리한다. TensorRT는 기존 _EngineSession을 이용하고 plugins와 profile_index를 전달하며 독립 보고 범위에서 실행한다. 다른 원시 backend는 기존 _Session과 GPU 연산 검증을 유지한다.

감지 요청은 기존 GPU 전처리·predictor·결과 복원을 감지 세션으로 옮겨 공개 YoloDetect 동작을 보존한다. 세션 재사용은 GPU와 profile별로 분리한다. 공통 루프가 큐 수집, 입력 완료 대기, 실패 세션 제거와 close, 프로파일 병합, 참조 해제 및 모든 요청 깨우기를 담당한다. 원시 출력은 배치 축과 GPU를 확인하고 요청별로 복제한다. 감지 결과도 기존 GPU 완료 이벤트 계약을 유지한다.

embedded/yolo_inference와 yolo_detect의 가져오기를 갱신하고 이전 두 모듈을 삭제한다. 기존 테스트의 내부 모듈 경로와 TensorRT backend 인자를 명시적으로 이관한다. tests/test_central_yolo_inference의 관찰 스레드명을 통일한다. 기존 TensorRT 옵션·실패 복구, legacy 감지·실제 pt/engine 및 세 backend 중앙 배치 검증을 실행한다. 현행 문서는 통합 모듈로 갱신하되 이전 완료 작업의 역사 기록은 보존한다. 새로운 의존성은 없다. 헌장 템플릿 검사는 생략하며 한글 문서 규칙을 준수한다.

### 검증 계약 보완

기존 수동 워커 fixture에 backend를 명시하고 요청 키의 profile_index를 확인한다. TensorRT 단계 mock은 통합 호출의 backend를 검증한다. 기존 개별 YoloDetect는 호출자의 cuda_stream에서 실행하며 생산 코드 변경 없이 유지한다. 이전부터 실패하던 별도 스트림 단정은 호출자 스트림과 GPU 좌표·CPU 복사 금지를 검증하도록 바로잡는다. 공통 원시 추론의 보고 시간은 GPU 완료 동기화까지 측정한다.

## 전후처리 예제 소유권 설계

사용자가 YoloDetect 삭제를 선택했다. image.py의 NV12 변환과 image_transform.py의 불변 ImageTransform을 yolo_pre_process.py의 모듈 수준 구현으로 이동한다. image_preprocessing.py의 설정·상수 캐시·프레임 읽기·변환·리사이즈·정규화·처리를 YoloPreProcess 메서드로 이동한다. detection_postprocessing.py의 이름 설정·입력 검증·필터/NMS·결과 생성·보고·정리를 YoloPostProcess 안으로 이동한다. TensorRT 예제는 Step 직접 상속·기존 이름/옵션을 유지하고 YOLO 예제의 생성자·메서드를 재사용하며 전처리 보고 종류만 TensorRT로 지정한다.

YoloDetect 모듈과 embedded export, CudaAsync의 legacy 분류를 삭제한다. local_yolo_inference에서 감지 전용 요청·세션·predictor·infer_detection·전처리 도우미를 제거하고 세 backend의 원시 단일 워커만 유지한다. 감지 경로 제거 후 embedded 도우미의 가져오기는 모듈 상단으로 복원할 수 있다. 코어의 inference_contract는 사용자 변환 객체를 조회하는 중립 계약으로 유지한다.

삭제된 감지 기능 전용 tests/test_yolo_detect.py·test_yolo_batch.py·test_local_yolo.py·test_yolo_model_ids.py는 정리한다. 좌표·GPU 전후처리·ID 보존은 기존 새 추론·후처리 테스트에서 계속 검증한다. 프레임 해제·보고·기본 설정·비동기·중앙 Source·Overlay 테스트의 유지 시나리오는 새 단계 조합으로 이관한다. 삭제 및 코어 독립 가져오기 검증을 먼저 추가한다. README와 docs의 이전 호출을 YoloInference와 예제 전후처리로 바꾸고 YoloDetect 레퍼런스 페이지/목록을 삭제한다. 기존 speckit 역사 기록은 보존하며 최신 요청이 이전 유지 요구를 대체한다. GPU 회귀와 세 backend 중앙 배치를 실행한다. 새 의존성은 없다.

### 이관 검증 보완

중앙 감지 Source를 예제 전처리·원시 추론·예제 후처리로 바꾸고 전용 서버 그룹에서 검증하여 운영 프로세스에 영향을 주지 않는다. 다중 스트림 예제의 삭제된 PostProcess 가져오기는 실제 존재하는 SaveInferenceResultToDB로 연결한다. 문서의 감지 필터 설정은 YoloPostProcess로, 실행 옵션은 YoloInference로 구분한다.

## 예제 메서드 직렬화 수정

main.run_remote의 register_step에서 타입의 MRO에 정의된 메서드 모듈을 함께 pickle-by-value로 등록한다. TensorRT 래퍼가 재사용한 YoloPreProcess/YoloPostProcess 메서드의 모듈도 포함한다. 파이프라인 연결부와 프로토콜 및 서버 경로는 변경하지 않는다. 새 subprocess에서 step 패키지를 차단하고 실제 전달 payload를 복원해 CPU 좌표·NMS 도우미를 호출하여 참조 누락을 재현한다.

## 범용 프레임 간격 설계: 2026-10-13

EveryNFrames(*steps, interval_frames=1)를 embedded/every_n_frames.py에 추가한다. 사용자 단계는 Hotswap(recover_errors=False)로 감싸고 steps/_hot_steps로 기존 중첩 구조를 유지한다. 실행마다 입력 카운터와 단계별 재사용 가능한 입력 슬롯·처리 생성기를 만든다. 선택 프레임만 슬롯에 전달하고 하나의 출력을 요구한다. 슬롯은 같은 요청의 재소비를 거부하며 종료 시 끝을 전달하여 추가 출력·미소비 출력도 검증한다. 오류·조기 종료 시 내부 생성기와 상류를 닫고 슬롯 참조를 해제한다. GPU 복사와 스레드는 추가하지 않는다.

YoloInference의 옵션·속성·간격 검증·세 경로 분기를 제거하고 삭제 YAML 키는 명확한 오류로 거부한다. 기존 backend·세션·공유 워커·프로파일 계약은 유지한다. 생략 프레임은 범용 래퍼가 손대지 않으며 이전 결과 재사용은 제공하지 않는다.

pipeline.py의 설정·감시·StreamReport 탐지와 main.py의 사용자 모듈 등록을 CudaAsync/EveryNFrames 양쪽에 재귀 적용한다. CudaAsync 보고 분류도 중첩 래퍼의 실제 추론 backend를 찾는다. 단일 예제는 CudaAsync(EveryNFrames(...))로, 다중 예제는 EveryNFrames(전처리, 추론, 후처리)로 감싸며 YAML에서 interval_frames를 지정한다. 기존 기본 간격 1을 유지한다. CudaAsync는 타임아웃 시 출력 프레임을 폐기할 수 있으므로 기본 비동기 예제는 간격 래퍼를 내부에 두어 계약 위반 오류가 외부 파이프라인을 종료하지 않도록 한다. 카운터는 비동기 작업자가 받은 입력을 기준으로 한다.

수정 범위는 embedded/every_n_frames.py·yolo_inference.py·cuda_async.py·__init__.py, pipeline.py, main.py, examples/01_single_stream_rtsp_style.py·02_multiple_stream_rtsp_style.py·config/stream.yml, 관련 tests 및 README.md·docs의 현행 API 안내다. tests/test_every_n_frames.py에 일반 단계·묶음·카운터·검증·생성기 수명·중첩 설정/직렬화 계약을 추가하고 기존 간격 테스트를 새 래퍼 또는 모든 입력 실행 계약으로 이관한다.

기술 맥락은 기존 Python 3.11.9와 unittest/CUDA이며 새 의존성은 없다. 헌장은 미작성 템플릿으로 검사를 생략한다. 한글 문서와 전 단계 절차를 준수하며 설계 전후 위반이 없다.

## 비동기 폐기 수정 설계

execution.py에 호출 범위의 비공개 폐기 표시 계약을 추가한다. EveryNFrames가 내부 반복자를 진행하는 동안만 표시 수신을 허용하고 CudaAsync는 실제 안전 판단으로 폐기할 때만 표시를 출력한다. 표시 타입은 Hotswap의 컨텍스트·epoch 전달과 호환되며 프레임·텐서 참조를 보관하지 않는다. 단독 CudaAsync는 기존처럼 폐기 후 다음 입력을 요청한다. EveryNFrames는 표시를 소비하여 후속 단계와 외부 출력에서 제거하고 다음 전체 입력으로 진행한다. 일반 단계는 기존 1입력1출력 계약을 계속 검증한다.

테스트는 tests/test_every_n_frames.py에서 차단된 원본·폐기 후 복구·busy·안전한 timeout·마지막 폐기·후속 단계 미실행과 실제 Pipeline._run_local 감시 경로를 재현한다. 기존 test_async.py·test_nvidia_decode.py의 GPU 원본 보호 회귀를 실행한다. docs의 기본 비동기 조합을 EveryNFrames(CudaAsync(...))로 갱신한다. 사용자가 바꾼 예제의 외부 간격 배치는 그대로 지원하고 삭제한 다중 예제 파일은 복원하지 않는다. 기술 의존성과 새 스레드는 추가하지 않는다. 헌장은 미작성 템플릿이며 한글 문서와 전체 speckit 절차를 유지한다.
