# 작업 목록: 배치 프로세스 별칭

## 1단계: 준비

- [X] T001 src/, tests/, examples/, README.md와 docs/의 development 사용처를 검토한다. (FR-001~FR-005)

## 2단계: 사용자 이야기 1

- [X] T002 [US1] tests/test_central_process.py의 별칭 기본값·유효성·직렬화 및 PID 공유·분리 검사를 갱신한다. (SC-001, SC-002)
- [X] T003 [US1] src/pipeworks/pipeline.py와 main.py에 batch_process 계약과 전달을 구현한다. (FR-001~FR-004)

## 3단계: 사용자 이야기 2

- [X] T004 [US2] tests/test_async.py 및 라우팅·원격 전달 검증을 새 필드에 맞춘다. (SC-001, SC-003)
- [X] T005 [US2] examples/01_single_stream_rtsp_style.py, README.md와 docs/pipeworks/의 사용법을 갱신한다. (FR-005)

## 4단계: 최종 검증

- [X] T006 관련 tests/와 실제 중앙 프로세스 검사를 실행하고 요구사항 대조 및 잔여 검색을 수행한다. (SC-001~SC-003)

## 의존성과 전략

T001 → T002 → T003 → T004 → T005 → T006 순서다. 테스트·문서 파일은 병렬 작업 가능하지만 이번에는 순차 수행한다. 최소 완성 범위는 두 사용자 이야기 전체다.

