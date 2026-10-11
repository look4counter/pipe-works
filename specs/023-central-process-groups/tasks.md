# 작업 목록: 중앙 프로세스 그룹 분리

입력: [명세](spec.md), [계획](plan.md), [계약](contracts/execution.md)

1~5단계는 이전 실행 옵션 계약으로 완료한 작업 이력이다. 현재 생성자 development 계약은 6단계에서 갱신한다.

## 1단계: 준비

- [x] T001 src/pipeworks/main.py와 .gitignore에서 Windows 실행 환경·기존 주소·무창 실행·무시 규칙을 확인한다.

## 2단계: 공통 기반

- [x] T002 src/pipeworks/main.py에 그룹 이름 검증과 기본 호환 주소·잠금 경로 계산을 구현한다. FR-002·003·005.

## 3단계: 운영·개발 분리 — 사용자 이야기 1

독립 검증: 같은 그룹의 PID 재사용, 다른 그룹의 PID 분리 및 개발 강제 종료 후 운영 지속.

- [x] T003 [US1] tests/test_central_process.py에 이름 거부·PID 분리·같은 그룹 재사용·개발 강제 종료 격리 검증을 추가한다. FR-001·002·005, SC-001·002.
- [x] T004 [US1] src/pipeworks/main.py에 연결·자동 시작·서버 명령행 그룹 전달을 구현한다. FR-001·002·003·004.
- [x] T005 [US1] src/pipeworks/pipeline.py의 run에 키워드 전용 server_group 옵션을 추가한다. FR-001.

## 4단계: 그룹별 수명 — 사용자 이야기 2

독립 검증: 동일 그룹 동시 시작과 개발 그룹의 유휴 종료·재시작 시 운영 지속.

- [x] T006 [US2] src/pipeworks/main.py의 서버 확인·리스너·유휴 종료 연결을 선택 그룹에 묶는다. FR-003·004.
- [x] T007 [US2] tests/test_central_process.py에 동시 시작·독립 유휴 종료·재시작 검증을 추가한다. SC-002·003.

## 5단계: 문서와 검증

- [x] T008 README.md, docs/pipeworks/pipeline.md, docs/pipeworks/main.md에 운영·개발 예와 batch=False 실행 위치·GPU 공유 경계를 문서화한다. FR-006.
- [x] T009 tests/test_central_process.py 및 tests/test_pipeline*.py를 실행하고 specs/023-central-process-groups/quickstart.md에 결과를 기록한다. SC-001·002·003.

## 의존성과 실행 전략

T001 → T002 → T003 → T004 → T005 → T006 → T007 → T008 → T009 순서로 실행한다. 사용자 이야기 2는 사용자 이야기 1의 주소 분리에 의존한다. 먼저 PID 분리로 최소 기능을 확인하고 수명·회귀 검증을 완료한다.

## 병렬 가능 작업

US1의 테스트 작성과 공개 옵션 작성은 서로 다른 파일이지만 테스트 실행은 구현 완료 후 수행한다. US2의 문서 작성과 수명 테스트 설계도 병렬 작업이 가능하다. 이번 실행에서는 순차 수행한다.

## 6단계: 생성자 개발 모드로 계약 갱신

- [x] T010 [US1] tests/test_central_process.py에 생성자 bool 검증·기본 False·직렬화 보존·인자 없는 run 및 운영·개발 PID 분리 검증을 갱신한다. FR-001·002·005.
- [x] T011 [US1] src/pipeworks/pipeline.py에 development=False 검증·저장을 추가하고 run 인자를 제거한다. src/pipeworks/main.py의 run_remote는 저장된 값으로 내부 그룹을 선택한다. FR-001·004·005.
- [x] T012 [US2] tests/test_central_process.py의 재시작 검증을 생성자 개발 모드 계약에 맞추고 기존 내부 종료 격리 검증을 유지한다. FR-003·004, SC-002.
- [x] T013 README.md, docs/pipeworks/pipeline.md, docs/pipeworks/main.md, specs/023-central-process-groups/quickstart.md를 생성자 development 계약으로 갱신한다. FR-006.
- [x] T014 tests/test_central_process.py와 tests/test_pipeline*.py 회귀를 실행하고 specs/023-central-process-groups/quickstart.md에 결과를 기록한다. SC-001·002·003.

T010 → T011 → T012 → T013 → T014 순으로 진행한다. 테스트·문서 파일 작성은 병렬 가능하나 이번에는 순차 실행한다.


