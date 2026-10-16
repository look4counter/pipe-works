# 작업 목록: 중앙 프로세스 정리 완료 대기

## 1단계: 준비

- [x] T001 specs/035-wait-pipeline-cleanup의 명세·계획·계약 및 src/pipeworks/main.py의 요청 수명과 유휴 타이머를 검토한다. (FR-001~006)

## 2단계: 공통 검증 기반

- [x] T002 tests/test_central_shutdown.py에 이벤트 기반 지연 정리와 고유 서버 그룹 검증 도구를 작성한다. (FR-005)

## 3단계: 사용자 스토리 1

- [x] T003 [US1] tests/test_central_shutdown.py에 연결 종료·생존 신호 만료·감시 예외 및 12초 이상 정리 지연 시 서버 생존 검증을 먼저 작성하고 기존 실패를 확인한다. (FR-001, FR-002, FR-003, FR-005, SC-001)
- [x] T004 [US1] src/pipeworks/main.py에서 실행 Thread를 보관하고 감시 루프 finally에서 중단 신호와 실제 스레드 종료 대기를 보장한다. (FR-001, FR-002, FR-003, FR-005)

## 4단계: 사용자 스토리 2

- [x] T005 [US2] tests/test_central_shutdown.py에서 느린 정리 중 같은 서버의 새 실행과 정리 후 유휴 종료를 검증하고 tests/test_central_process.py의 정상·오류·그룹 분리 검증을 실행한다. (FR-004, SC-002, SC-003)

## 5단계: 문서와 최종 확인

- [x] T006 docs/pipeworks/main.md에 실제 정리 완료 대기와 무기한 정리의 유휴 종료 동작을 반영한다. (FR-006)
- [x] T007 specs/035-wait-pipeline-cleanup/quickstart.md에 검증 결과를 기록하고 명세·계획·작업의 구현 충족 여부를 점검한다. (FR-005, SC-001~003)

## 의존성과 구현 전략

T001 → T002 → T003 → T004 → T005 → T006 → T007 순서로 수행한다. 사용자 스토리 1의 종료 보장을 먼저 구현한 후 사용자 스토리 2의 동시 요청과 기존 계약을 검증한다. T004 이후 문서 작업은 검증과 독립적으로 수행할 수 있으나 이번 작업은 순차 수행한다.
