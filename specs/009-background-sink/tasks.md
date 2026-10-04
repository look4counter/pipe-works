# 작업 목록: 단일 작업자 Sink

**명세**: [spec.md](spec.md)  
**계획**: [plan.md](plan.md)

## 단계 1: 계약 준비

- [x] T001 [US1] `src/pipeworks/embedded/sink.py`의 Step 반복자와 `Hotswap` 연결 계약을 확인한다. (FR-001, FR-002)

## 단계 2: 구현

- [x] T002 [US1] `src/pipeworks/embedded/sink.py`에 단일 입력 슬롯과 지속 작업자를 구현한다. (FR-001~FR-005)
- [x] T003 [US1] `src/pipeworks/embedded/sink.py`에 오류 기록과 종료 처리를 구현한다. (FR-006, FR-007)

## 단계 3: 검증

- [x] T004 [US1] 이벤트 기반 동시성 확인으로 비차단 전달, 작업 중 건너뛰기, 이후 재수락을 검증한다. (SC-001~SC-004)
- [x] T005 [US1] 기존 단위 테스트와 문법 검사를 실행한다. (FR-001~FR-007)

## 단계 4: 내부 Step 핫스왑

- [x] T006 [US3] `src/pipeworks/embedded/sink.py`에서 내부 Step을 핫스왑으로 감싸고 중복 감싸기를 방지한다. (FR-008, FR-009)
- [x] T007 [US3] 실제 파일 변경을 이용해 작업 완료 후 새 구현 적용과 주 스트림 유지를 확인한다. (SC-005)
