# 작업 목록: 실행별 프레임 처리 보고

## 단계 5: 남은 이름 정리

- [x] T020 폐기한 이름과 파일 경로를 요구사항 및 다른 명세에서 정리한다. (FR-018)
- [x] T021 보고 모듈을 옮기고 모든 소스 및 테스트 import를 갱신한다. (FR-018)
- [x] T022 공개 보고 동작과 전체 테스트를 검증하고 명세와 구현을 재대조한다. (FR-018)

## 단계 4: 보고 단계 통합

- [x] T017 `StreamReport`의 컨텍스트 전달과 두 줄 보고를 검증한다. (FR-005, FR-008, FR-017)
- [x] T018 구형 보고 클래스와 공개 내보내기를 제거한다. (FR-009, FR-017)
- [x] T019 구형 단계 전용 테스트를 정리하고 관련 회귀 테스트를 실행한다. (FR-017)

## 단계 3: 추론 시간 명확화

- [x] T013 배치 모델 실행 구간과 요청별 시간 전달을 검증하는 테스트를 추가한다. (FR-014~FR-016)
- [x] T014 `local_yolo.py`에서 예측 시작부터 GPU 완료까지 측정하고 기존 반환 계약을 유지한다. (FR-014~FR-016)
- [x] T015 `YoloDetectBatch`와 `YoloDetect`의 통계 기록 구간을 실제 예측 실행으로 통일한다. (FR-014~FR-016)
- [x] T016 관련 테스트를 실행하고 명세와 구현의 차이를 점검한다. (FR-014~FR-016)

**명세**: [spec.md](spec.md)
**계획**: [plan.md](plan.md)

- [x] T001 프레임 시작·완료와 인코딩 시간을 기록한다. (FR-001, FR-002)
- [x] T002 실행별 수집기와 독립 호출의 기본 수집기를 둔다. (FR-003)
- [x] T003 공통 YOLO 추론 건수와 시간을 기록한다. (FR-006)
- [x] T004 실행된 단계의 시간만 평균에 포함한다. (FR-007)
- [x] T005 `StreamReport`가 두 줄 보고를 출력하고 같은 패킷 객체를 전달한다. (FR-004, FR-005, FR-008, FR-009)
- [x] T006 보고 형식, 구간 초기화, 실행별 분리와 패킷 전달을 테스트한다. (SC-001~SC-005)

## 단계 2: 마지막 단계 영상 상태 보고

- [x] T007 [US1] `tests/test_report.py`에 수신·송신 상태 전환과 출력 없는 상류에서의 주기 보고를 검증한다. (FR-010~FR-013)
- [x] T008 [US1] `src/pipeworks/embedded/stream_report.py`에 실행별 상태 수집과 `StreamReport`를 구현한다. (FR-010, FR-012, FR-013)
- [x] T009 [US1] `src/pipeworks/embedded/rtsp_source.py`와 `src/pipeworks/embedded/rtsp_publish.py`에 실제 패킷 성공·실패 기록을 연결한다. (FR-011)
- [x] T010 [US1] `src/pipeworks/embedded/__init__.py`에서 새 단계를 공개하고 `examples/01_single_stream_rtsp_style.py`, `examples/02_multiple_stream_rtsp_style.py`의 마지막 단계로 등록한다. (FR-010, SC-006)
- [x] T011 [US1] `tests/test_central_process.py`에서 중앙 프로세스의 보고 출력 전달과 종료 정리를 검증한다. (SC-008)
- [x] T012 `tests/test_report.py`, `tests/test_rtsp_source.py`, `tests/test_rtsp_publish.py` 및 관련 전체 테스트를 실행하고 `specs/010-stream-report/quickstart.md`와 대조한다. (SC-006~SC-008)

## 의존성

- T007에서 현재 실패를 확인한 뒤 T008~T010을 수행한다. T011과 T012는 공개 단계와 예제 변경 후 실행한다.
