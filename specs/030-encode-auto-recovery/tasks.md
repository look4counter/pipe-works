# 작업 목록: 인코더 자동 복구

**입력**: [명세](spec.md), [계획](plan.md), [조사](research.md)

## 1단계: 준비

- [X] T001 .gitignore와 tests/test_report.py의 인코더 시험 계약 및 로컬 GPU 실행 환경을 확인한다.

## 2단계: 기반

- [X] T002 tests/test_nvidia_encode.py에 정상 패킷·자동 복구·반복 실패·1초 경계·로그·종료·오류 분리 회귀 시험을 먼저 작성하고 실패를 확인한다. FR-001, FR-002, FR-005, FR-006.

## 3단계: 사용자 이야기 1 — 오류 후 재개

**독립 검증**: 일시 및 반복 실패 후 새 프레임이 출력되고 패킷 시각이 증가한다.

- [X] T003 [US1] src/pipeworks/embedded/nvidia_encode.py에 네이티브 오류 경계·재시도·PTS/DTS 유지·복구 기록·정리 순서를 구현한다. FR-001, FR-002, FR-003, FR-005, FR-006.
- [X] T004 [US1] tests/test_nvidia_encode.py에서 실제 GPU 오류 주입 후 새 세션의 패킷을 독립 디코딩하여 시작 프레임·헤더와 연속 시간을 검증한다. FR-003, SC-002.

## 4단계: 사용자 이야기 2 — 입력 변경과 종료

**독립 검증**: 스트림과 영상 형식 변경 시 새 인코더 및 출력 메타데이터를 확인하고 중지 대기 시간을 검증한다.

- [X] T005 [US2] tests/test_nvidia_encode.py에 스트림·코덱·해상도·픽셀 형식·CUDA 스트림 교체 및 외부 자원 수명 시험을 작성하고 src/pipeworks/embedded/nvidia_encode.py에 변경 감지를 구현한다. FR-004, FR-005.

## 5단계: 문서 및 최종 검증

- [X] T006 docs/pipeworks/embedded/nvidia_encode.md와 docs/reference/NvidiaEncode.html에 재시도·복구·입력 변경 및 보장 한계를 반영한다. FR-006.
- [X] T007 specs/030-encode-auto-recovery/quickstart.md에 따른 인코더·디코더·송출·통계·설정·수명·처리 경계 시험 및 구문 검사를 수행한다. SC-001~004.

## 의존성과 실행 순서

T001 → T002 → T003 → T004 → T005 → T006 → T007 순서로 수행한다. 같은 파일 변경은 순차 진행한다. 문서 읽기와 연구는 독립 수행할 수 있지만 구현 작업은 병렬로 나누지 않는다.

## 구현 전략

기본 복구를 우선 완성하고 실제 GPU 출력 재생을 확인한 뒤 입력 변경과 정리 경계를 검증한다. 마지막에 speckit-converge로 잔여 요구사항을 확인한다.
