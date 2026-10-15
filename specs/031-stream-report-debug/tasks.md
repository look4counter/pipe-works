# 작업 목록: StreamReport 디버그 로그

## 1단계: 준비

- [X] T001 src/pipeworks/embedded/stream_report.py와 tests/test_report.py의 기존 출력 계약 및 .gitignore를 확인한다.

## 2단계: 사용자 이야기 1

- [X] T002 [US1] src/pipeworks/embedded/stream_report.py의 직접 출력을 DEBUG 로그로 변경하고 tests/test_report.py의 기존 출력 검증을 로깅 캡처로 갱신한다. FR-001~003.

## 3단계: 문서와 검증

- [X] T003 docs/pipeworks/embedded/stream_report.md에 DEBUG 로그 설정을 설명하고 specs/031-stream-report-debug/quickstart.md에 따른 시험과 구문·공백 검사를 수행한다. SC-001~002.

## 의존성과 실행 전략

T001 → T002 → T003 순서로 수행한다. 작은 단일 출력 경계 변경이므로 구현을 순차 진행한다. 통계 계산을 변경하지 않으며 기존 시험을 활용한다.

## 4단계: 단일 스트림 예제 설정

- [X] T004 [US1] examples/01_single_stream_rtsp_style.py의 직접 실행 진입점에 DEBUG 기본 로깅을 파이프라인 생성 전에 설정하고 구문 및 실행 순서를 검증한다. FR-004, SC-003. 기존 T003 이후 수행한다.

## 5단계: YoloReport 디버그 기록

- [X] T005 [US1] src/pipeworks/embedded/yolo_report.py의 콘솔 출력을 모듈 DEBUG 로그로 변경하고 tests/test_detection_report.py의 메시지·마지막 보고·INFO 필터링 검증을 갱신한다. FR-005, SC-004. T004 이후 수행한다.
- [X] T006 docs/pipeworks/embedded/yolo_report.md의 로깅 설정을 갱신하고 감지 통계 및 일반 통계 회귀 시험과 구문·공백 검사를 수행한다. FR-005, SC-004. T005 이후 수행한다.

## 6단계: 중앙 프로세스 중복 실행 안내

- [X] T007 src/pipeworks/main.py의 중복 실행 안내를 logger.warning으로 변경하고 기존 문자열·반환 동작·WARNING 수준을 검증한다. FR-006, SC-005. T006 이후 수행한다.
