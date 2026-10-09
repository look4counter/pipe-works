# 실행 작업: TensorRT 추론 전용 단계

**명세**: [spec.md](spec.md)
**계획**: [plan.md](plan.md)

## 1단계: 준비

- [x] T001 `specs/013-tensor-rt-inference/checklists/requirements.md`와 설계 문서 및 `.gitignore`의 구현 준비 상태를 확인한다.

## 2단계: 기반

- [x] T002 `tests/test_tensor_rt_inference.py`에 엔진·컨텍스트·레지스트리·할당기 API 모형과 GPU 데이터 검증 기반을 준비한다.

## 3단계: US1 추론 전용 단계

독립 검증: 임의 이름의 GPU 입력으로 실행하고 원시 GPU 출력 사전을 동일 컨텍스트에 전달한다.

- [x] T003 [US1] `tests/test_tensor_rt_inference.py`에 입력·출력·자료형·형상·GPU·비동기 지연·실패·통계·종료·간격 검증을 작성한다. (FR-001~FR-005, FR-008~FR-012)
- [x] T004 [US1] `src/pipeworks/embedded/tensor_rt_inference.py`에 Step·설정·단일 작업자·GPU 입력 복제와 TensorRT 이름 기반 실행을 구현한다. (FR-002~FR-005, FR-008~FR-012)
- [x] T005 [US1] `src/pipeworks/embedded/__init__.py`에서 `TensorRTInference`를 공개한다. (FR-001)

## 4단계: US2 동적 엔진과 플러그인

독립 검증: 동적·빈 출력과 내장·외부 플러그인 초기화를 지원하고 누락 시 영상 전달을 유지한다.

- [x] T006 [US2] `tests/test_tensor_rt_inference.py`에 동적 출력·정렬·빈 출력·프로파일·플러그인·메타데이터와 실제 엔진 조건부 검증을 작성한다. (FR-006, FR-007, SC-003, SC-005, SC-006)
- [x] T007 [US2] `src/pipeworks/embedded/tensor_rt_inference.py`에 GPU 출력 할당기·동적 형상·플러그인 등록 및 엔진 메타데이터 처리를 구현한다. (FR-006, FR-007)

## 5단계: 검증과 안내

- [x] T008 `tests/test_tensor_rt_inference.py` 및 기존 YOLO·배치·공유 GPU 검증을 실행한다. (SC-001~SC-007)
- [x] T009 `docs/pipeworks/embedded/tensor_rt_inference.md`, `README.md`, `specs/013-tensor-rt-inference/quickstart.md`에 사용·설정·제약·검증 결과를 기록한다.
- [x] T010 `specs/013-tensor-rt-inference/tasks.md`와 코드를 수렴 점검하고 필요한 보완 작업을 완료한다.

## 의존성과 실행 전략

T001 → T002 → T003 → T006 → T004 → T005 → T007 → T008 → T009 → T010 순서다. US2는 US1의 엔진 실행 기반을 사용한다. 두 시나리오가 전체 요청의 완성 범위다. T005와 T009는 실행 코드 완성 뒤 독립된 파일에서 수행할 수 있으나 이번에는 순서대로 처리한다. 동일 실행 파일의 변경은 순차 처리한다.
