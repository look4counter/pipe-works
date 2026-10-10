# 작업 목록: 실행별 프레임 처리 보고

## 단계 9: 기록 비용 절감

- [x] T040 명세·명확화·계획과 조사 자료를 갱신하고 FR-026~028, SC-013의 일관성을 분석한다.
- [x] T041 `tests/test_report.py`에 저빈도 발행·누적 기록·무수집·공유 작업자 종료 검증을 추가하고 직접 조회 테스트를 갱신한다. (SC-013)
- [x] T042 `src/pipeworks/embedded/stream_report.py`에서 가변 누적 기록과 공용 발행 작업자 및 불변 읽기를 구현한다. (FR-023~028)
- [x] T043 `src/pipeworks/pipeline.py`, `src/pipeworks/embedded/tap.py`에서 보고자 감지·수집 활성 상태·문맥 전파를 연결하고 관련 테스트를 갱신한다. (FR-028)
- [x] T044 관련 회귀와 기록 비용을 측정하고 문서·검증 기록 및 수렴 점검을 완료한다. (SC-013)

의존성: T040 → T041 → T042 → T043 → T044. 분석 결과 새 요구에 누락·충돌·미해결 질문은 없다. 이전 완료 항목은 이력으로 유지한다.

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
## 최근 10초 동시 표시 작업

- [x] T030 명세·명확화·계획 일관성을 분석한다. (FR-020~021)
- [x] T031 StreamReport에 최근 표본·평균·출력을 구현하고 결정적 시계 회귀를 추가한다. (SC-010)
- [x] T032 관련 회귀·문서 갱신·수렴 점검을 완료한다. (SC-010)

T030 → T031 → T032 순서로 수행한다.
## 표기 변경

- [x] T033 명세·명확화·계획 일관성을 확인한다. (FR-022)
- [x] T034 출력 문자열·테스트·검증 기록을 갱신하고 보고 회귀와 수렴 점검을 완료한다. (FR-022)

T033 → T034 순서로 수행한다.

## 단계 6: 읽기 전용 보고 준비

- [x] T035 `tests/test_report.py`에 보고 측 잠금 금지·스냅샷 불변·독립 보고자·다중 기록·청크 보관 한계와 경계 테스트를 먼저 추가한다. (FR-023~025, SC-011~012)

## 단계 7: 읽기 전용 보고 사용자 시나리오

- [x] T036 [US1] `src/pipeworks/embedded/stream_report.py`의 기록 함수에 누적 불변 스냅샷과 초별 불변 이력을 구현한다. (FR-003, FR-024~025)
- [x] T037 [US1] `src/pipeworks/embedded/stream_report.py`에 보고자별 차분 관측을 구현하고 StreamReport의 통계 잠금과 공유 자료 수정을 제거한다. (FR-023~025, SC-011)
- [x] T038 [US1] `tests/test_report.py`의 기존 초기화 테스트를 차분 관측으로 갱신하고 `tests/test_tensor_rt_inference.py`, `tests/test_yolo_detect.py`의 내부 통계 조회를 스냅샷 경로로 갱신한다. 보고·감지·비동기·RTSP·중앙 프로세스 회귀를 검증한다. (SC-001~012)

## 단계 8: 문서와 전체 검증

- [x] T039 `docs/pipeworks/embedded/stream_report.md`, `specs/010-stream-report/quickstart.md`에 기록/표시 책임과 잠금 범위·검증 결과를 기록하고 전체 테스트를 실행한다. (FR-023~025, SC-012)

T035 → T036 → T037 → T038 → T039 순서로 수행한다. 기존 완료 작업을 보존한다. T038의 서로 독립된 테스트 파일은 병렬 실행할 수 있다. 최소 완료 범위는 읽기 전용 보고 이야기 전체이며 출력·이력 정확성과 회귀까지 검증한다.
