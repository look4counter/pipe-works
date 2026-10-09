# 구현 계획: TensorRT 추론 전용 단계

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
