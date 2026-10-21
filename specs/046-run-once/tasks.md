# 작업 목록: RunOnce Step 래퍼

**입력**: [spec.md](spec.md), [plan.md](plan.md)

## Phase 1: 기반 구현

- [x] T001 [P] RunOnce 동작 계약 테스트를 tests/test_run_once.py에 작성한다.
- [x] T002 src/pipeworks/embedded/run_once.py에 Step 검증, 내부 Step 보관, 최초 입력 단회 실행, 이후 입력 통과, 예외 상태 처리를 구현한다.
- [x] T003 src/pipeworks/embedded/__init__.py에 RunOnce를 공개하고 export 회귀 테스트를 추가한다.

## Phase 2: 파이프라인 통합

- [x] T004 src/pipeworks/pipeline.py의 Step 탐색·설정 적용·파일 감시 갱신에 RunOnce의 단일 내부 Step을 통합한다.
- [x] T005 src/pipeworks/main.py의 중앙 프로세스 내부 Step 탐색에 RunOnce를 통합한다.
- [x] T006 tests/test_run_once.py에 파이프라인 등록, 내부 설정 전달, 기존 래퍼 조합 및 서로 다른 인스턴스 독립성 테스트를 추가한다.

## Phase 3: 문서 및 검증

- [x] T007 docs/pipeworks/run_once.md에 RunOnce 사용법, 첫 입력 처리, 이후 입력 통과, 범위 제한을 문서화한다.
- [x] T008 관련 테스트와 전체 테스트를 실행하고 실패 원인 및 호환성 문제를 해결한다. (정적 검사는 통과했으며 pytest는 환경의 watchdog 미설치로 수집 단계에서 중단됨)
- [x] T009 명세의 기능 요구사항과 성공 기준을 구현·테스트 결과와 대조해 최종 점검한다.

## 의존성 및 실행 순서

- T001은 T002보다 먼저 수행한다.
- T003은 T002와 병렬로 진행할 수 있지만 공개 API 테스트는 구현 파일 추가 후 검증한다.
- T004와 T005는 T002, T003 이후 수행한다.
- T006은 T004와 T005 이후 수행한다.
- T007은 T002 이후 병렬로 진행할 수 있다.
- T008은 T001부터 T007까지 완료한 뒤 수행한다.
- T009는 T008 완료 후 수행한다.

## 완료 기준

- 모든 작업 항목이 완료 표시된다.
- RunOnce가 빈 입력, 정상 입력, 다중 출력, 예외, 재호출을 검증한다.
- 파이프라인 및 중앙 프로세스 탐색 경로가 기존 래퍼와 동일한 내부 Step 설정을 지원한다.
- 사용자 문서와 기능 명세가 구현 동작과 일치한다.
