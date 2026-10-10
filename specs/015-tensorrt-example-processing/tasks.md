# 작업 목록

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
