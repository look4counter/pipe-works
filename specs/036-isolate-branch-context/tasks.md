# 작업 목록: 분기 컨텍스트 분리

## 1단계: 준비

- [x] T001 specs/036-isolate-branch-context의 명세·계획·계약과 기존 슬롯·핫스왑 경계를 확인한다. (FR-001~006)

## 2단계: 검증 기반

- [x] T002 tests/test_tap_skip_if_busy.py에 임시 파일 핫스왑과 입력·자원 동일성 검증 도구를 준비한다. (FR-006)

## 3단계: 사용자 스토리 1

- [x] T003 [US1] tests/test_tap_skip_if_busy.py에 실제 배경 코드 교체·주 경로 누적 유지·양방향 속성 격리·공통 상류 정보 보존 검증을 먼저 작성해 기존 실패를 확인한다. (FR-001, FR-002, FR-003, SC-001)
- [x] T004 [US1] src/pipeworks/embedded/tap_skip_if_busy.py에서 수락한 입력만 별도 PipelineContext로 저장한다. (FR-001, FR-002, FR-003)

## 4단계: 사용자 스토리 2

- [x] T005 [US2] tests/test_tap_skip_if_busy.py에서 실제 배경 처리의 원본 출력·자원 공유·바쁨 생략·종료 동작을 검증한다. (FR-004, FR-005, SC-002, SC-003)

## 5단계: 문서 및 최종 검증

- [x] T006 docs/pipeworks/embedded/tap_skip_if_busy.md, docs/pipeworks/hotswap.md, README.md에 속성 격리와 공유 데이터 읽기 전용 계약을 반영한다. (FR-006)
- [x] T007 관련 tests 회귀 검증을 실행하고 specs/036-isolate-branch-context/quickstart.md에 결과를 기록한다. (FR-006, SC-003)

## 의존성과 수행 전략

T001 → T002 → T003 → T004 → T005 → T006 → T007 순서로 수행한다. 사용자 스토리 1의 실제 코드 교체 격리를 먼저 확인하고 사용자 스토리 2의 자원 공유와 생략을 검증한다. 구현 후 문서와 독립 회귀 검증은 병행 가능하지만 이번 작업은 순차 수행한다.
