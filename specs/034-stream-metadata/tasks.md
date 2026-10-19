# 작업 목록: 비디오 스트림 수명 분리

## 1단계: 준비

- [x] T001 specs/034-stream-metadata의 명세·연구·계약과 로컬 PyAV API를 확인한다. (FR-001~007)

## 2단계: 공통 기반

- [x] T002 tests/test_video.py에 불변 값·원본 종료·실제 h264/hevc 헤더 복원 검증을 먼저 작성한다. (FR-001, FR-004, FR-007)
- [x] T003 src/pipeworks/video.py에 불변 코덱·스트림 값 모델과 송출 복원 도우미를 구현한다. (FR-001, FR-004, FR-006)

## 3단계: 사용자 스토리 1

- [x] T004 [US1] tests/test_rtsp_source.py에 1,000개 패킷 재사용·종료 후 접근·원본 미포함 검증을 작성하고 src/pipeworks/embedded/rtsp_source.py에서 연결당 복사를 적용한다. (FR-001, FR-002, FR-007, SC-001, SC-002)

## 4단계: 사용자 스토리 2

- [x] T005 [US2] tests/test_nvidia_encode.py에서 실제 출력 헤더·세대 공유·지연 출력 검증을 작성하고 src/pipeworks/embedded/nvidia_encode.py의 출력 메타데이터를 분리한다. (FR-003, FR-005)
- [x] T006 [US2] tests/test_rtsp_publish.py의 메타데이터 계약·동일 설정 재연결 검증을 작성하고 src/pipeworks/embedded/rtsp_publish.py에서 독립 값으로 출력 스트림을 생성한다. (FR-003, FR-004, FR-007)

## 5단계: 문서와 검증

- [x] T007 README.md와 docs/pipeworks/models.md 및 embedded의 소스·인코딩·디코딩·송출 문서를 새 값 계약에 맞춘다. (FR-006)
- [x] T008 tests의 관련 및 전체 회귀 검증을 실행하고 specs/034-stream-metadata/quickstart.md에 결과·환경 한계를 기록한다. (FR-007, SC-003)

## 의존성과 수행 전략

T001 → T002 → T003 → T004 → T005 → T006 → T007 → T008 순서로 수행한다. 공통 모델 완료 후 소스와 송출 테스트는 독립 검증할 수 있으나 이번 구현은 순차 수행한다. 사용자 스토리 1을 먼저 검증한 뒤 출력·재연결을 완성한다.

## 6단계: 생성 검증 제거 준비

- [x] T009 specs/034-stream-metadata/spec.md와 plan.md의 FR-008 및 데이터 계약을 검토하고 구현 전 일관성을 분석한다.

## 7단계: 사용자 스토리 1 보완

독립 검증: 빈 이름과 0 및 음수 크기의 직접 생성·스트림 복사가 원본 값을 보존한다.

- [x] T010 [US1] tests/test_video.py의 거부 검증을 원본 값 보존 검증으로 변경하고 부가 데이터 독립 복사 검증을 유지한다. (FR-008, SC-004)
- [x] T011 [US1] src/pipeworks/video.py의 이름·크기 검사와 ValueError를 제거하고 extradata 변환은 유지한다. (FR-008)

## 8단계: 회귀 검증과 수렴

- [x] T012 tests/test_video.py, tests/test_rtsp_source.py, tests/test_rtsp_publish.py를 실행하고 specs/034-stream-metadata/quickstart.md에 결과를 기록한 뒤 수렴을 확인한다. (FR-007, FR-008, SC-003, SC-004)

보완 작업은 T009 → T010 → T011 → T012 순서다. 최소 제공 범위는 사용자 스토리 1의 생성 예외 제거다. 테스트 명령들은 독립 실행할 수 있으나 변경과 확인은 순차 수행한다.

## 9단계: RTSP 메타정보 복구 준비

- [x] T013 specs/034-stream-metadata/spec.md와 plan.md 및 계약을 분석해 FR-009~011의 작업 대응과 품질 점검을 확인한다.

## 10단계: 사용자 스토리 3 — 비정상 연결 재생성

독립 검증: 비정상 연결들을 닫고 간격을 지켜 새 연결을 열며 정상 연결의 패킷만 전달한다.

- [x] T014 [US3] tests/test_rtsp_source.py에 비디오 부재·이름·크기·복사 실패·시간 정보 오류 복구와 연속 실패·정상 재개·reconnect=False·중단·취소·무관한 오류 전파를 검증한다. (FR-009~011, SC-005~006)
- [x] T015 [US3] src/pipeworks/embedded/rtsp_source.py에서 연결당 메타정보를 확인하고 복구 신호를 처리해 닫힘·공통 대기·재생성을 수행한다. (FR-009~011)

## 11단계: 문서와 회귀 검증

- [x] T016 docs/pipeworks/embedded/rtsp_source.md에 메타정보 검사·재생성 조건과 reconnect 옵션의 적용 범위를 반영한다. (FR-010~011)
- [x] T017 specs/034-stream-metadata/quickstart.md의 관련 회귀를 실행해 결과를 기록하고 명세·계획·작업과 코드의 수렴을 확인한다. (SC-005~006)

의존성은 T013 → T014 → T015 → T016 → T017이다. 최소 제공 범위는 사용자 스토리 3의 입력 연결 복구 전체다. 회귀 테스트 명령은 독립 실행 가능하며 파일 변경은 순차 수행한다.
