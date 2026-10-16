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
