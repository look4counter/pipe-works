# 작업 목록

## 단계 15: YOLO 공통 ID 준비

- [x] T033 specs/015-tensorrt-example-processing/의 FR-022~024·SC-011·계획·계약 일관성을 분석한다.

## 단계 16: 사용자 시나리오 6 — YOLO ID별 결과

- [x] T034 [US6] src/pipeworks/embedded/yolo_detect.py에 id 구성·원자적 검증·입력별 사전 복사·ID별 결과 교체를 두 실행 경로에 구현한다. (FR-022~024)
- [x] T035 [US6] tests/test_yolo_detect.py·tests/test_yolo_batch.py를 사전 계약에 맞추고 tests/test_yolo_model_ids.py에서 직렬·혼합·오류·구성 변경·비동기·Overlay를 검증한다. (SC-011)
- [x] T036 [US6] docs/pipeworks/embedded/yolo_detect.md·docs/pipeworks/models.md·README.md·examples/config/stream.yml과 공통 계약의 결과 읽기 안내를 갱신한다. (FR-023)

## 단계 17: 최종 검증

- [x] T037 tests/test_local_yolo.py·test_detection_report.py·test_box_overlay.py·test_tensor_rt_model_ids.py·test_step_config_defaults.py·test_async.py·test_frame_release.py 회귀를 실행하고 specs/015-tensorrt-example-processing/quickstart.md에 결과를 기록한다. (SC-011)

의존성: T033 → T034 → T035 → T036 → T037. 최소 구현과 최종 전달은 US6 전체다. T034 이후 기존 결과 테스트 갱신과 문서 작성은 독립적으로 가능하나 한 작업자가 순차 수행한다.

## 단계 12: 직렬 모델 결과 식별 준비

- [x] T027 specs/015-tensorrt-example-processing/의 FR-018~021·SC-010·계획·계약 일관성을 분석한다.

## 단계 13: 사용자 시나리오 5 — 모델 ID별 결과와 표시

- [x] T028 [US5] src/pipeworks/embedded/tensor_rt_inference.py에 id 구성·검증·컨텍스트 전달을 구현하고 src/pipeworks/embedded/tensor_rt_pre_process.py의 결과 초기화를 제거한다. (FR-018, FR-019)
- [x] T029 [US5] examples/step/tensor_rt_post_process.py에 ID별 결과 교체·사전 격리·model_id 정리를 구현한다. (FR-019, FR-021)
- [x] T030 [US5] examples/step/box_overlay.py의 id 선택·ID별 이전 결과·YOLO 단일 객체 호환을 구현한다. (FR-020)
- [x] T031 [US5] tests/test_tensor_rt_model_ids.py와 tests/test_tensor_rt_processing.py 및 tools/benchmark_postprocess.py를 새 계약에 맞추고 ID·직렬·배치·Overlay·비동기 회귀를 검증한다. (SC-010)

## 단계 14: 안내와 최종 점검

- [x] T032 examples/config/stream.yml·docs/pipeworks/embedded/tensor_rt_inference.md·tensor_rt_preprocess.md·specs/015-tensorrt-example-processing/contracts/model-ids.md·quickstart.md에 ID별 결과 사용과 마지막 Overlay 배치·검증 결과를 기록한다.

의존성: T027 → T028 → T029 → T030 → T031 → T032. 최소 구현과 최종 전달 모두 US5 전체를 포함한다. T029 이후 추론 ID 검증과 Overlay 구현은 독립적으로 가능하지만 한 작업자가 순서대로 진행한다.

## 단계 11: 모듈 파일명 변경

- [x] T024 specs/015-tensorrt-example-processing/의 FR-017·SC-009·계획·계약 일관성을 분석한다.
- [x] T025 [US4] src/pipeworks/embedded/tensor_rt_pre_process.py로 이동하고 src/pipeworks/embedded/__init__.py·examples/01_single_stream_rtsp_style.py·tests/test_image_transform.py·tests/test_tensor_rt_preprocess_optimized.py·tools/benchmark_preprocess.py의 현재 경로를 갱신한다.
- [x] T026 [US4] specs/015-tensorrt-example-processing/contracts/preprocess.md의 경로를 갱신하고 관련 회귀와 수렴 점검 결과를 quickstart.md에 기록한다.

T024 → T025 → T026 순서로 수행한다. 단일 시나리오 전체가 최소 구현이며 독립 검증은 새 모듈 가져오기와 기존 전처리·좌표 복원·후처리 테스트다.

- [x] T001 명세·명확화·계획을 분석하여 형식과 수용 기준의 일관성을 확인한다. (FR-001~004)
- [x] T002 두 사용자 Step과 YAML 설정 및 단일 예제를 구현한다. (FR-001~004)
- [x] T003 합성 GPU 전후처리·예제와 실제 엔진 검증을 실행한다. (SC-001~002)
- [x] T004 결과를 기록하고 수렴 점검으로 남은 차이를 확인한다. (SC-001~002)

T001 → T002 → T003 → T004 순서로 수행한다.
## 스트림·버퍼 후속 작업

- [x] T005 명세·명확화·계획을 갱신하고 일관성을 분석한다. (FR-005~006)
- [x] T006 전후처리의 별도 스트림과 입력 생산자 연결 및 버퍼 정리를 구현한다. (FR-005~006)
- [x] T007 CUDA 스트림·정리·실제 엔진·Async 검증과 수렴 점검 결과를 기록한다. (SC-003)

T005 → T006 → T007 순서로 수행한다.

## 단계 3: 준비와 공통 기반

- [x] T008 specs/015-tensorrt-example-processing/의 명세·명확화·설계·계약·작업을 분석하고 차단 충돌이 없는지 확인한다. (FR-007~012)

## 단계 4: 사용자 시나리오 1 — 모델별 입력 규칙

- [x] T009 [US1] tests/test_tensor_rt_preprocess.py에 구성·생성자/YAML 우선순위·잘못된 입력과 CUDA 수치 검증을 작성하고 구현 전 실패를 확인한다. (FR-008~011, SC-004)
- [x] T010 [US1] src/pipeworks/image.py로 기존 NV12 변환을 분리하고 src/pipeworks/local_yolo.py의 기존 함수 이름을 보존한다. (FR-010)
- [x] T011 [US1] src/pipeworks/embedded/tensor_rt_preprocess.py에 옵션 검증·세 가지 크기 변환·정규화·출력 구성을 구현하고 embedded/__init__.py에서 내보낸다. (FR-007~012)

## 단계 5: 사용자 시나리오 2 — 기존 파이프라인 호환

- [x] T012 [US2] examples/step/tensor_rt_pre_process.py를 내장 클래스 재수출로 바꾸고 examples/01_single_stream_rtsp_style.py와 examples/config/stream.yml을 연결한다. (FR-007, FR-012)
- [x] T013 [US2] tests/test_tensor_rt_processing.py 및 tests/test_frame_release.py, test_detection_report.py, test_async.py, test_local_yolo.py, test_yolo_detect.py, test_box_overlay.py의 관련 검증을 실행하고 실패를 해결한다. (SC-005)

## 단계 6: 안내와 최종 검증

- [x] T014 README.md와 docs/pipeworks/embedded/tensor_rt_preprocess.md에 전체 옵션·입출력·탐지 및 분류 예제·수치 한계를 안내한다. (SC-006)
- [x] T015 tests/ 회귀 검증과 git diff 검사를 실행하고 specs/015-tensorrt-example-processing/quickstart.md에 결과와 환경 한계를 기록한다. (SC-004~006)

의존성: T008 → T009 → T010 → T011 → T012 → T013 → T014 → T015. 최소 구현 범위는 US1 전체이고 최종 전달은 US2 호환과 안내도 포함한다. GPU 수치 검증은 모델 엔진 없이 독립 실행한다. T011 이후 문서 작성은 예제·회귀 검증과 독립적으로 가능하다. 여러 작업자가 같은 파일을 동시에 수정하지 않는다.

## 단계 7: 전체 YAML 옵션 노출

- [x] T016 specs/015-tensorrt-example-processing/의 FR-013·SC-007·계획·작업 일관성을 분석한다.
- [x] T017 [US1] examples/config/stream.yml에 TensorRTPreProcess의 15개 옵션을 기본값과 한글 안내 주석으로 노출한다. (FR-013)
- [x] T018 examples/config/stream.yml의 옵션 완전성과 기본값 적용을 검증하고 specs/015-tensorrt-example-processing/quickstart.md에 결과를 기록한다. (SC-007)

T016 → T017 → T018 순서로 수행하고 완료 후 수렴 점검한다. 독립 검증은 GPU 작업 없이 YAML의 키와 구성 값으로 수행한다.

## 단계 8: 좌표 복원 객체 준비

- [x] T019 specs/015-tensorrt-example-processing/의 FR-014~016·SC-008·설계·계약 일관성을 분석한다.

## 단계 9: 사용자 시나리오 3 — 전처리와 후처리의 좌표 책임 분리

- [x] T020 [US3] src/pipeworks/image_transform.py에 불변 변환 객체와 축별 제자리 복원을 구현하고 src/pipeworks/embedded/tensor_rt_preprocess.py에서 생성한다. (FR-014, FR-016)
- [x] T021 [US3] examples/step/tensor_rt_post_process.py에서 좌표 계산을 제거하고 복원을 위임하며 tools/benchmark_postprocess.py의 변환 생성을 갱신한다. (FR-015)
- [x] T022 [US3] tests/test_image_transform.py·tests/test_tensor_rt_postprocess_optimized.py·tests/test_tensor_rt_processing.py에 세 변환 수치·빈 결과·경계·부가 열·대체 변환 위임 검증을 작성하고 관련 회귀를 실행한다. (SC-008)

## 단계 10: 안내와 수렴

- [x] T023 docs/pipeworks/embedded/tensor_rt_preprocess.md의 복원 계약을 갱신하고 specs/015-tensorrt-example-processing/quickstart.md에 검증 결과를 기록한다. (FR-015, SC-008)

의존성: T019 → T020 → T021 → T022 → T023. 최소 구현은 US3 전체이며 문서까지 완료한다. T021 이후 문서 초안과 변환 수치 검증은 독립 실행할 수 있다. 별도 작업자는 사용하지 않는다.
