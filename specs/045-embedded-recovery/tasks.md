# 작업 목록: 내장 단계 복구

## 1단계: 준비

- [x] T001 specs/045-embedded-recovery/spec.md와 plan.md·계약의 일관성 및 품질 점검을 확인한다. (FR-001~006)

## 2단계: 공통 기반

- [x] T002 src/pipeworks/embedded/recovery.py에 장애 분류와 추론 복구 반복자를 작성하고 tests/test_embedded_recovery.py에서 일반·치명 오류 경계를 검증한다. (FR-003, FR-005)

## 3단계: 사용자 스토리 1

독립 검증: 비정상 패킷 뒤 정상 입력을 처리하고 재연결 간격과 자원 정리를 유지한다.

- [x] T003 [US1] src/pipeworks/embedded/rtsp_source.py와 rtsp_publish.py에 실행 오류 복구를 연결하고 tests/test_rtsp_source.py·test_rtsp_publish.py의 정책 검증을 갱신한다. (FR-001, FR-006)
- [x] T004 [US1] src/pipeworks/embedded/nvidia_decode.py와 nvidia_encode.py에 입력·출력 오류 복구를 추가하고 tests/test_nvidia_decode.py·test_nvidia_encode.py를 갱신한다. (FR-002, FR-005~006)

## 4단계: 사용자 스토리 2

독립 검증: 일반 추론·내부 단계 오류 후 영상과 다음 정상 결과를 전달하며 GPU 오류는 호출자에게 전파한다.

- [x] T005 [US2] src/pipeworks/embedded/yolo_inference.py와 every_n_frames.py에 원본 통과·반복자 재생성을 적용하고 tests/test_yolo_inference.py·test_every_n_frames.py를 갱신한다. (FR-003~004, FR-006)
- [x] T006 [US2] src/pipeworks/embedded/cuda_async.py와 tap_skip_if_busy.py의 작업 스레드에서 GPU 오류 전달을 보완하고 tests/test_embedded_recovery.py에 회귀 검증을 추가한다. (FR-005~006)

## 5단계: 검증과 문서

- [x] T007 docs/pipeworks/embedded의 해당 단계 오류 계약을 갱신하고 specs/045-embedded-recovery/quickstart.md에 관련 테스트 결과를 기록한 뒤 수렴을 확인한다. (FR-006, SC-001~002)

## 의존성과 전략

T001 → T002 → T003 → T004 → T005 → T006 → T007 순서로 수행한다. 최소 제공 범위는 두 사용자 스토리 전체다. 관련 테스트 파일은 독립 실행 가능하나 같은 소스에 대한 변경은 순차 진행한다.

## 6단계: 수렴 보완

- [x] T008 src/pipeworks/embedded/yolo_inference.py에서 입력 소비 전 세션 초기화 실패에도 모델 식별자를 부여하고 tests/test_embedded_recovery.py로 후처리 계약을 검증한다. (FR-003, 부분 구현)
- [x] T009 src/pipeworks/embedded/yolo_report.py와 stream_report.py의 부가 보고 실패가 영상 처리를 종료하지 않도록 보완하고 tests/test_embedded_recovery.py·보고 회귀 및 문서로 검증한다. (FR-006, 부분 구현)
