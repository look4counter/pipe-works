# 작업 목록: 모델 설정 경로 명시

## 1단계: 준비와 기반

- [X] T001 src/pipeworks/의 설정 경로 사용처와 tests/의 기존 계약을 검토한다. (FR-001~FR-004)

## 2단계: 사용자 이야기 1

- [X] T002 [US1] tests/test_explicit_model_config.py에 명시 파일, 기본값, 누락 파일 및 경로 분리 검증을 추가한다. (SC-001, SC-002)
- [X] T003 [US1] src/pipeworks/embedded/yolo_inference.py, yolo_backend.py, yolo_backends/tensorrt.py에 config_path를 적용한다. (FR-001~FR-003)

## 3단계: 사용자 이야기 2

- [X] T004 [US2] src/pipeworks/local_yolo_inference.py에서 설정 전달과 작업자 캐시 격리를 구현한다. (FR-003, FR-004)
- [X] T005 [US2] tests/의 자동 탐색 의존 호출과 examples/, docs/의 설정 예제를 갱신한다. (FR-005)

## 4단계: 검증

- [X] T006 관련 tests/를 실행하고 전체 요구사항과 구현의 일치를 확인한다. (SC-001~SC-003)

## 의존성과 구현 전략

T001 → T002 → T003 → T004 → T005 → T006 순서로 수행한다. 최소 완성 범위는 두 사용자 이야기 전체이며 파일 간 호출 계약을 함께 갱신한다. 독립 문서 편집은 병렬 가능하지만 이번에는 순차 작업한다.


## 5단계: 구현 후 대조 검토

- [X] T007 tests/test_remote_example_dependencies.py에서 직렬화된 요청의 pipeline 필드를 추출하도록 검증 코드를 갱신하고 재실행한다. (SC-003, FR-005, 부분 충족)

대조 결과: 모델 설정 경로 기능은 구현되었으나 관련 회귀 검사에서 기존 테스트가 요청 사전 자체를 파이프라인으로 취급하여 실패했다. 현재 중앙 요청 계약에 맞추는 검증 보완 작업이다.

