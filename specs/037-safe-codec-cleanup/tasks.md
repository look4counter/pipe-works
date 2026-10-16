# 작업 목록: 코덱 정리와 병렬 송신 안전성

## 1단계: 준비

- [x] T001 specs/037-safe-codec-cleanup의 명세·계획·연구·계약과 기존 복구 검증을 확인한다. (FR-001~008)

## 2단계: 공통 검증 기반

- [x] T002 tests/test_codec_cleanup.py에 버퍼 풀·완료 이벤트·부분 실패와 코덱 정리 주입 도구를 작성한다. (FR-008)

## 3단계: 사용자 스토리 1

- [x] T003 [US1] tests/test_codec_cleanup.py에서 일부 반환 실패 뒤 성공 포인터가 재반환되는 기존 오류를 재현하고 src/pipeworks/embedded/nvidia_decode.py의 반환 성공 상태를 즉시 갱신한다. (FR-001, SC-001)

## 4단계: 사용자 스토리 2

- [x] T004 [US2] tests/test_codec_cleanup.py에 최초 오류 보존·동기화 1회·실패 풀 재사용 금지·외부 참조 종료 검증을 작성한다. (FR-002, FR-003, FR-004, SC-002)
- [x] T005 [US2] src/pipeworks/embedded/nvidia_decode.py와 src/pipeworks/embedded/nvidia_encode.py에 정리 실패 상태를 적용하여 네이티브 재진입을 막고 기존 정상 해제 순서를 유지한다. (FR-002, FR-003, FR-004)

## 5단계: 사용자 스토리 3

- [x] T006 [US3] tests/test_rtsp_publish.py를 실제 av.Packet 기반으로 갱신하고 원본 불변·시간/부가 데이터 복사·장벽 기반 동시 송신·실제 파일 mux·재디코딩 검증을 추가한다. (FR-005, FR-006, FR-007, SC-003)
- [x] T007 [US3] src/pipeworks/embedded/rtsp_publish.py에 독립 압축 패킷 복사를 적용하고 보정·출력 스트림 변경을 복제에만 수행한다. (FR-005, FR-006, FR-007)

## 6단계: 문서와 최종 검증

- [x] T008 docs/pipeworks/embedded/nvidia_decode.md, nvidia_encode.md, rtsp_publish.md와 docs/pipeworks/models.md에 정리 실패와 패킷 불변·복사 비용·지원 플래그 계약을 반영한다. (FR-008)
- [x] T009 관련 tests의 기존 복구·GPU 수명·핫스왑·송신 회귀 검증을 수행하고 specs/037-safe-codec-cleanup/quickstart.md에 결과를 기록한다. (FR-004, FR-008, SC-004)

## 의존성과 수행 전략

T001 → T002 → T003 → T004 → T005 → T006 → T007 → T008 → T009 순서로 수행한다. 사용자 요청 순서대로 세 스토리를 완성한다. 독립 문서와 검증은 병행 가능하지만 구현은 순차로 진행한다.
