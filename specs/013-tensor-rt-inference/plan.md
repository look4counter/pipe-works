# 구현 계획: TensorRT 추론 전용 단계

## 영상별 프로파일 이동 계획

Python 3.11·기존 CUDA/TensorRT 실행 기반을 유지한다. tensor_rt_inference.py의 configure에 profile_index 검증과 원자적 갱신을 추가하고 개별 세션 재생성 키를 (gpu_id, profile_index)로 변경한다. 모델 설정은 plugins만 반환하며 이전 profile_index·timeout 키를 이동·변경 안내 오류로 거부한다. local_tensor_rt.py의 infer는 profile_index 키워드 인자를 받아 요청·호환 키·세션 키에 반영하며 실패 시 해당 세션만 제거한다. GPU 스트림은 GPU별로 유지하고 같은 작업자에서 순차 실행한다.

local_yolo.py와 local_tensor_rt.py는 모델 YAML의 timeout_ms를 읽고 기존 밀리초 변환·기본값·유효성 검증을 유지한다. tests/test_tensor_rt_inference.py와 test_local_tensor_rt.py에 설정 원자성·실행 중 변경·프로파일별 분리·실패 격리·실엔진 검증을 이전하고 test_local_yolo.py에 새 시간 명칭과 경계값을 반영한다. README·TensorRT 및 YOLO 안내·examples/config/stream.yml·examples/model/yolo11n.yml를 갱신한다. 외부 의존성 변경은 없고 헌법 템플릿 검사는 생략한다. 한글 문서와 speckit 순서를 준수한다.

## 모델 실행 옵션 계획

동적 입력은 선택 프로파일의 get_tensor_profile_shape 최소·최대 형상으로 선검증한다. 실제 범위 밖 입력에서 set_input_shape가 성공을 반환할 수 있어 후속 infer_shapes까지 잘못된 입력을 넘기지 않는다.

FR-031~034는 기존 Python 3.11·PyTorch CUDA·TensorRT 10.10에서 구현한다. tensor_rt_inference.py에 모델 YAML 읽기와 프로파일·플러그인 검증 함수를 공통으로 두고 local_tensor_rt.py도 사용한다. _EngineSession은 프로파일 번호를 저장하고 역직렬화 이후 엔진 범위를 검증하며 선택 프로파일의 텐서 포맷을 검사한다. 첫 infer에서 실행 스트림의 set_optimization_profile_async로 선택 후 형상을 설정한다. 실패는 호출자의 기존 동기 완료 정리로 전달한다. 기존 플러그인 로딩 순서와 수명은 유지한다.

tests/test_tensor_rt_inference.py에 설정 경계값·모형 엔진의 선택 순서·실패·범위와 실제 다중 프로파일 엔진의 두 모드 검증을 추가한다. tests/test_local_tensor_rt.py는 공통 설정·작업자 전달과 기존 수집 회귀를 확인한다. docs/pipeworks/embedded/tensor_rt_inference.md, README.md, examples/model/yolo11n.yml에 사용법을 기록한다. 새 외부 의존성은 없고 헌법은 미작성 템플릿이므로 원칙 검사는 생략한다. 문서는 한글이며 실행 중 설정 재로딩은 포함하지 않는다.

## 프레임 간격 명칭 변경 계획

FR-027~030을 위해 Python 3.11의 기존 configure 검증·생성 기본값·개별 및 배치 선택 분기를 `inference_interval_frame`으로 이전한다. 이전 키는 configure 시작에서 거부하여 설정 변경의 원자성을 유지한다. tests/test_tensor_rt_inference.py의 기존 간격 테스트를 이전하고 기본값·전체 경계값·이전 키 동시 지정의 검증을 보강한다. README.md, docs/pipeworks/embedded/tensor_rt_inference.md, examples/config/stream.yml의 설정과 이전 안내를 갱신한다. 검증은 가상환경의 unittest로 TensorRT·예제 처리·YOLO·배치·설정 관련 회귀를 실행한다. 헌법은 미작성 템플릿이므로 원칙 검사는 생략하고 한글 문서와 speckit 순서를 준수한다. 외부 의존성이나 엔진 API 변경은 없다.

## 요약

입력 GPU 텐서를 엔진에서 발견한 이름에 연결하고 모든 원시 출력을 이름별 GPU 텐서 사전으로 반환한다. TensorRT 10 이름 기반 실행 API와 별도 작업자·CUDA 스트림을 사용한다.

## 기술 문맥과 규칙 점검

Python 3.11, PyTorch 2.2 CUDA 및 프로젝트 의존성 TensorRT 10.10을 사용한다. 실제 환경에는 TensorRT와 엔진 파일이 없어 모의 TensorRT API와 실제 GPU 텐서로 계약을 검증하며 실엔진 검증은 조건부 수행한다. TensorRT는 작업자 초기화에서 지연 가져오기하므로 패키지 전체 가져오기에 영향을 주지 않는다. 헌법은 미작성 템플릿으로 구체적인 원칙 검사는 적용하지 않는다. 한글 문서와 speckit 순서 및 기존 비동기 GPU 계약을 준수한다.

## 연구와 구현 설계

### 기반

`src/pipeworks/embedded/tensor_rt_inference.py`에 Step·엔진 실행기·요청·작업자를 정의한다. 기존 `yolo_detect._AsyncWorker`의 슬롯 확보·제출·종료 기반을 상속하고 작업자 실행 루프는 TensorRT 실행기로 교체한다. YOLO의 모델·영상 변환·필터·예측기는 호출하지 않는다.

### 엔진과 플러그인

표준 플러그인을 초기화하고 Runtime의 엔진 포함 실행 코드를 허용한다. 동명 YAML의 외부 플러그인 목록은 runtime 플러그인 레지스트리에 로드하며 핸들과 Runtime·엔진·컨텍스트를 보관한다. 일반 엔진과 앞부분의 유효한 Ultralytics JSON 메타데이터를 읽는다. 엔진 생성·자료형 변환은 하지 않는다.

### GPU 바인딩과 출력

`num_io_tensors`와 이름·모드·자료형·형상·장치·포맷 API로 바인딩을 조사한다. GPU 위치와 LINEAR 형식만 허용한다. 단일 텐서는 입력 하나에 자동 매핑하고 사전은 이름 집합의 완전 일치를 검증한다. 자료형과 GPU를 확인하고 입력 형상을 설정하여 프로파일 0 범위를 검증한다.

입력 주소를 설정한 뒤 `infer_shapes`를 확인한다. 출력별 GPU 할당기를 연결해 알려진 형상과 데이터 의존 형상을 모두 처리한다. `IOutputAllocator`의 동기·비동기 재할당과 형상 알림을 구현하고 정렬·0바이트·자료형·출력 strides 및 수명을 관리한다. `execute_async_v3`에 PyTorch 스트림 핸들을 전달하고 작업자에서만 완료를 기다린다.

### 비동기 계약과 설정

GPU 입력을 생산자 스트림에서 연속 복제하고 준비 이벤트를 기록한다. 제공된 `cuda_stream`이 없으면 해당 GPU의 현재 스트림을 사용한다. 작업자가 이벤트를 기다리고 입력을 사용한다. 원본과 복제의 수명은 완료까지 보관한다. 모델 동명 YAML의 timeout 기본값은 5ms이며 plugins는 문자열 경로 목록이다. 클래스명 YAML의 gpu_id·inference_interval은 기존 검증과 기본값을 따른다.

제한 시간 안 완료된 출력만 해당 컨텍스트에 기록한다. 사용 중·지연·실패는 None이고 늦은 결과는 폐기한다. 작업자 초기화·정지·종료·재실행에도 슬롯과 작업자 수를 1개로 유지한다. 복사한 실행 문맥으로 실제 추론 통계를 기록한다.

## 코드 구조와 검증

- `src/pipeworks/embedded/tensor_rt_inference.py`: 전용 단계와 엔진 실행.
- `src/pipeworks/embedded/__init__.py`: 공개 내보내기.
- `tests/test_tensor_rt_inference.py`: 가짜 TensorRT 엔진·레지스트리·할당기와 실제 GPU 데이터로 값·바인딩·설정·플러그인·동적 형상·실패·비동기 수명 검증.
- `docs/pipeworks/embedded/tensor_rt_inference.md`, `README.md`: 단계 사용·설정·제약 안내.

검증은 새 단계와 기존 YOLO·배치·공유 GPU 경로에 한정한다. 설계 문서는 [연구](research.md), [데이터](data-model.md), [계약](contracts/inference.md), [실행 안내](quickstart.md)로 나눈다. 설계 후 규칙 위반이나 미해결 사항은 없다.
## 동기 실행 계획

내부 _Request·_InferenceWorker를 제거한다. process별 별도 CUDA 스트림과 지연 생성 엔진 세션을 보관하고 GPU·플러그인 변경 경계에서 재생성한다. 입력 장치 검증 후 생산자 완료 이벤트를 기록·확인하고 연속화가 필요한 입력만 복사한다. _EngineSession.infer의 완료 동기화와 통계를 유지한다. finally에서 스트림 완료 후 세션을 닫는다. 실패는 Async 또는 호출자에 전달한다. tests/test_tensor_rt_inference.py의 비동기 전용 검증은 Async 조합·동기 실행 검증으로 이전하고 나머지 엔진 회귀를 보존한다. 실제 예제 plan 검증과 문서·README·Async 안내를 갱신한다.
## 배치 연결 계획

생성자에 키워드 batch를 추가한다. batch=True는 기존 입력 검증·생산자 준비 확인 후 현재 실행 스트림에 완료 이벤트를 기록하여 local_tensor_rt.infer에 전달한다. 간격 선택과 model_output 초기화는 기존과 동일하고 record_inference 콜백을 넘긴다. TensorRTInference는 자체 엔진 세션을 배치 경로에서 만들지 않는다. 기본 경로는 유지한다. tests/test_tensor_rt_inference.py에 모의 공유 실행기 연결 검증을 추가하고 관련 CUDA 회귀와 문서를 갱신한다.

## NMS 보호 복제 제거 계획

범위는 examples/step/tensor_rt_post_process.py의 NMS 입력과 tests/test_tensor_rt_processing.py의 기존 CUDA 결과 검증 및 관련 안내다. 현재 설치된 Ultralytics NMS는 원시 출력의 박스 좌표를 제자리 변환하며 검출 결과는 별도 선별된 텐서로 반환한다. TensorRTInference는 실행마다 출력 할당기를 만들고 공유 배치는 요청별 결과를 분리하므로 해당 예제의 원시 출력은 다른 요청과 공유하지 않는다.

기존 결과 테스트에 clone 금지 조건과 원시 좌표 변환 확인, detections의 신뢰도·클래스·BoxOverlay 표시를 추가해 기존 구현이 실패함을 먼저 확인한다. 이후 prediction.clone()을 prediction으로 바꾸고 원시 출력의 단독 소비 계약을 기록한다. 실제 plan·기존 후처리 실패 정리·CudaAsync 타임아웃 회귀를 실행하고 수렴 점검한다. 헌법은 미작성 템플릿이며 확장 후크는 없다. 최신 요청이 예제 후처리만 확장하며 추론기의 전처리·후처리 미수행 계약은 유지한다.
