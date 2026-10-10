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
## 동기 실행 후속 작업

- [x] T020 명세·명확화·계획·작업의 일관성을 분석한다. (FR-020~022)
- [x] T021 내부 비동기 구현을 동기 추론·무복제 입력·플러그인 설정으로 바꾸고 테스트를 새 계약으로 이전한다. (FR-020~022)
- [x] T022 실제 엔진·Async·예제 회귀와 문서 갱신을 수행한다. (SC-010)
- [x] T023 검증 결과 기록 후 수렴 점검한다. (SC-010)

T020 → T021 → T022 → T023 순서로 수행한다.
## 배치 연결

- [x] T024 명세·명확화·계획의 일관성을 분석한다. (FR-023~024)
- [x] T025 생성자·공유 배치 분기·GPU 이벤트·통계와 테스트를 구현한다. (SC-011)
- [x] T026 기본·공유 모듈 회귀·문서·수렴 점검을 완료한다. (SC-011)

T024 → T025 → T026 순서로 수행한다.

## NMS 보호 복제 제거

- [x] T027 명세·명확화·계획·계약과 작업 목록을 갱신하고 일관성을 분석한다. (FR-025~026)
- [x] T028 tests/test_tensor_rt_processing.py의 기존 CUDA 검증에 무복제·원시 출력 소비·BoxOverlay 연결을 추가하고 기존 구현의 실패를 확인한다. (SC-012)
- [x] T029 examples/step/tensor_rt_post_process.py에서 NMS 전 clone을 제거하고 원시 출력 단독 소비 안내를 갱신한다. (FR-025~026)
- [x] T030 예제 후처리·실제 plan·BoxOverlay·CudaAsync 회귀 검증과 수렴 점검을 완료한다. (SC-012)

T027 → T028 → T029 → T030 순서로 수행한다.

## 6단계: US3 프레임 간격 명칭 통일

독립 검증: 새 설정의 기본값·검증·두 모드 선택과 이전 키 거부를 확인한다.

- [x] T031 [US3] specs/013-tensor-rt-inference의 명세·명확화·설계·작업을 갱신하고 구현 전 일관성을 분석한다. (FR-027~030)
- [x] T032 [US3] tests/test_tensor_rt_inference.py의 간격 이름을 이전하고 기본값·경계값·이전 키 거부·상태 보존을 검증한다. (FR-027~029, SC-013)
- [x] T033 [US3] src/pipeworks/embedded/tensor_rt_inference.py의 공개 속성·설정·두 분기를 새 이름으로 바꾸고 이전 키를 거부한다. (FR-027~029)
- [x] T034 [US3] README.md, docs/pipeworks/embedded/tensor_rt_inference.md, examples/config/stream.yml의 이름과 이전 안내를 갱신한다. (FR-030)
- [x] T035 [US3] TensorRT·예제 처리·YOLO·배치·설정 회귀를 실행하고 specs/013-tensor-rt-inference/quickstart.md에 결과를 기록한 뒤 수렴 점검한다. (SC-013)

의존성: T031 → T032 → T033 → T034 → T035. T033 이후 T034는 테스트 실행과 독립적으로 수행 가능하다. 이번 변경의 최소 완성 범위는 US3 전체이며 기존 완료 작업은 유지한다.

## 7단계: US4 모델 YAML 실행 옵션

독립 검증: 프로파일 1과 플러그인을 지정해 개별·배치 모두 설정을 전달하고 잘못된 설정을 거부한다.

- [x] T036 [US4] specs/013-tensor-rt-inference의 명세·명확화·계획·계약·작업을 갱신하고 일관성을 분석한다. (FR-031~034)
- [x] T037 [US4] tests/test_tensor_rt_inference.py, tests/test_local_tensor_rt.py에 설정·프로파일 선택 순서·실패·두 경로·실제 다중 프로파일 엔진 검증을 추가하고 변경 전 실패를 확인한다. (FR-031~033, SC-014)
- [x] T038 [US4] src/pipeworks/embedded/tensor_rt_inference.py와 src/pipeworks/local_tensor_rt.py에 공통 설정 검증과 프로파일 전달·선택·범위 검증을 구현한다. (FR-031~033)
- [x] T039 [US4] README.md, docs/pipeworks/embedded/tensor_rt_inference.md, examples/model/yolo11n.yml에 옵션 사용과 기본값·경로·재시작 안내를 갱신한다. (FR-034)
- [x] T040 [US4] TensorRT·공유 배치·예제 처리·수집·CudaAsync 회귀를 실행하고 specs/013-tensor-rt-inference/quickstart.md에 결과를 기록한 뒤 수렴 점검한다. (SC-014)

의존성: T036 → T037 → T038 → T039 → T040. 구현 완료 후 T039와 회귀 실행은 서로 다른 파일에서 독립 수행 가능하다. 이번 최소 완성 범위는 US4 전체다.

## 8단계: US5 영상별 프로파일과 시간 명칭

독립 검증: 영상별 프로파일을 같은 모델의 개별·배치 경로에 적용하고 timeout_ms로 배치 수집 대기를 설정한다.

- [x] T041 [US5] specs/013-tensor-rt-inference 명세·명확화·계획·설계·작업을 갱신하고 일관성을 분석한다. (FR-035~038)
- [x] T042 [US5] tests/test_tensor_rt_inference.py, tests/test_local_tensor_rt.py, tests/test_local_yolo.py의 설정·변경·프로파일별 분리·실패 격리·시간 검증을 작성하고 변경 전 실패를 확인한다. (SC-015)
- [x] T043 [US5] src/pipeworks/embedded/tensor_rt_inference.py, src/pipeworks/local_tensor_rt.py, src/pipeworks/local_yolo.py에 영상별 프로파일과 timeout_ms 및 이전 키 안내를 구현한다. (FR-035~038)
- [x] T044 [US5] examples/config/stream.yml, examples/model/yolo11n.yml, README.md, docs/pipeworks/embedded/tensor_rt_inference.md, docs/pipeworks/embedded/yolo_detect.md와 관련 테스트 설정을 이전한다. (FR-038)
- [x] T045 [US5] TensorRT·YOLO·공유 배치·CudaAsync·설정 회귀를 실행하고 specs/013-tensor-rt-inference/quickstart.md에 결과를 기록한 뒤 수렴 점검한다. (SC-015)

의존성: T041 → T042 → T043 → T044 → T045. 구현 이후 문서 안내와 회귀 실행은 독립 수행 가능하다. US5 전체가 이번 최소 완성 범위다.

## 9단계: 고정 입력 메타데이터 캐시

- [x] T046 명세·명확화·계획을 갱신하고 캐시 수명 조사와 요구 일관성을 분석한다. (FR-039~040)
- [x] T047 `tests/test_tensor_rt_inference.py`에서 초기 조회·반복 조회 금지·고정/동적 검증과 실행별 출력 정보를 검증한다. (SC-016)
- [x] T048 `src/pipeworks/embedded/tensor_rt_inference.py`의 초기화에 입력 메타데이터 캐시를 추가하고 _bind에서 재사용한다. (FR-039~040)
- [x] T049 TensorRT·공유 배치 회귀를 실행하고 공개 문서·검증 기록 및 코드 수렴 점검을 완료한다. (SC-016)

의존성: T046 → T047 → T048 → T049. 분석 결과 요구의 누락·충돌·미해결 질문은 없다. 이전 작업과 다른 사용자 변경은 유지한다.
