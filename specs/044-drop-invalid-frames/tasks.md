# 작업 목록: 잘못된 NV12 프레임 폐기

## 단계 1: 준비

- [x] T001 specs/044-drop-invalid-frames/spec.md와 plan.md 및 기존 입력 소유권 규약을 확인한다.

## 단계 2: 기반 확인

- [x] T002 src/pipeworks/execution.py의 기존 폐기 신호와 src/pipeworks/embedded/every_n_frames.py의 소비 규약을 확인한다.

## 단계 3: 사용자 이야기 1 — 영상 처리 지속

목표와 독립 검증: 정상·비정상·정상 입력의 정상 출력 두 개 및 연속 폐기를 확인한다.

- [x] T003 [US1] tests/test_invalid_frame_drop.py에 크기별 폐기·재개·원본 불변성과 비동기·주기 실행 회귀 검증을 추가한다. FR-001, FR-002, FR-005.
- [x] T004 [US1] examples/step/yolo_pre_process.py와 examples/step/box_overlay.py에서 NV12 크기 오류만 프레임 단위로 폐기한다. FR-001, FR-002.
- [x] T005 [US1] src/pipeworks/embedded/cuda_async.py에서 내부 폐기 범위와 후속 단계 차단 및 외부 폐기 신호 처리를 연결한다. FR-005.

## 단계 4: 사용자 이야기 2 — 오류 구분과 진단

목표와 독립 검증: 경고와 프로파일 정리를 확인하고 다른 오류가 기존대로 처리되는지 검증한다.

- [x] T006 [US2] tests/test_invalid_frame_drop.py에서 경고·프로파일 정리·크기 외 오류와 설정 검증을 확인한다. FR-003, FR-004.
- [x] T007 [US2] examples/step/yolo_pre_process.py와 examples/step/box_overlay.py에서 폐기 경고와 프로파일 정리를 구현한다. FR-003, FR-004.

## 단계 5: 검증과 마무리

- [x] T008 specs/044-drop-invalid-frames/quickstart.md의 관련 테스트를 실행하고 명세·계획·코드 수렴을 확인한다.

## 의존성과 실행 전략

T001 → T002 → T003 → T004 → T005 → T006 → T007 → T008 순서로 진행한다. 최소 제공 범위는 사용자 이야기 1이다. 같은 파일을 수정하는 작업이므로 구현은 순차 수행한다. 병렬 기회는 구현 후 독립된 기존 테스트 모듈 검증이다. 두 사용자 이야기 모두 완료한 후 전달한다.
