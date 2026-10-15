# 작업 목록: 중앙 프로세스 구조화 로그 중계

## 1단계: 준비

- [X] T001 src/pipeworks/main.py, tests/test_central_process.py, tests/test_async.py와 .gitignore의 기존 통신·출력 계약을 확인한다.

## 2단계: 기반

- [X] T002 tests/test_remote_logging.py에 정책·직렬화·예외·수신 필터·출력 버퍼·문맥·연결 실패 시험을 먼저 작성하여 실패를 확인한다. FR-001~005, FR-007.
- [X] T003 src/pipeworks/remote_logging.py에 실행별 로그 정책·중계·직렬화·수신 및 stdout 어댑터를 구현한다. FR-001~005, FR-007.

## 3단계: 사용자 이야기 1 — 호출자 로깅

- [X] T004 [US1] src/pipeworks/main.py의 프로토콜과 요청 봉투·로그 응답·중계 실행 범위를 구현하고 tests/test_async.py의 직렬화 계약을 갱신한다. FR-001, FR-002, FR-005, FR-006.
- [X] T005 [US1] tests/test_central_process.py에서 실제 프로세스의 이름·수준·출처·예외·모듈별 필터·호환 print와 수신 핸들러를 검증한다. SC-001, SC-003.

## 4단계: 사용자 이야기 2·3 — 실행 격리와 print

- [X] T006 [US2] src/pipeworks/main.py의 _use_output_writer에 route 전파·중첩 복원을 추가하고 tests/test_remote_logging.py 및 tests/test_central_process.py에서 동시 정책·CudaAsync·TapSkipIfBusy·종료 정리를 검증한다. FR-003~005, SC-002.

## 5단계: 문서와 회귀

- [X] T007 docs/pipeworks/main.md 및 docs/pipeworks/embedded/stream_report.md, docs/pipeworks/embedded/yolo_report.md에 호출자 설정·추가 필드·print DEBUG 호환·범위를 반영한다. FR-001~007.
- [X] T008 specs/032-central-log-relay/quickstart.md의 관련 회귀·구문·공백 검사를 수행하고 결과를 기록한다. SC-001~004.

## 의존성과 전략

T001 → T002 → T003 → T004 → T005 → T006 → T007 → T008 순서로 진행한다. 같은 파일 변경은 순차 수행한다. 먼저 독립 로그 경계를 검증한 뒤 실제 중앙 실행과 동시 실행을 검증하고 마지막 speckit-converge로 차이를 확인한다.
