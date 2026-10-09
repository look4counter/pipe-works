# 작업 목록: 감지 성능 리포트

## 1단계: 준비

- [x] T001 `tests/test_detection_report.py`에 통계·이벤트·실행 격리 계약 검증을 작성한다. (FR-008)

## 2단계: 기반

- [x] T002 `src/pipeworks/detection_profile.py`, `src/pipeworks/embedded/stream_report.py`에 실행별 제한된 통계와 CPU/GPU 프로파일을 구현한다. (FR-003, FR-006, FR-007)

## 3단계: 사용자 이야기 1

- [x] T003 [US1] `src/pipeworks/embedded/yolo_detect_report.py`, `tensor_rt_report.py`, `__init__.py`에 주기 출력과 공개 Step을 구현한다. (FR-001, FR-004)
- [x] T004 [US1] `src/pipeworks/embedded/yolo_detect.py`, `src/pipeworks/local_yolo.py`에 단일·배치 구간 및 predictor 계측을 연결한다. (FR-002, FR-003, FR-006)
- [x] T005 [US1] `src/pipeworks/embedded/tensor_rt_inference.py`, `src/pipeworks/local_tensor_rt.py`, `examples/step/tensor_rt_pre_process.py`, `tensor_rt_post_process.py`에 동일 기준 계측을 연결한다. (FR-002, FR-003, FR-006)

## 4단계: 사용자 이야기 2

- [x] T006 [US2] `src/pipeworks/embedded/cuda_async.py`와 감지 경로에 완료·부분 종료·건너뜀·바쁨·타임아웃·오류 상태를 기록한다. (FR-005)
- [x] T007 [US2] `tests/test_detection_report.py`에서 리포트 정체·종료·비동기 및 배치 통계 격리를 검증한다. (FR-005, FR-006, SC-002, SC-004)

## 5단계: 마무리

- [x] T008 `examples/01_single_stream_rtsp_style.py`, `README.md`, `docs/pipeworks/embedded/detection_report.md`에 사용법과 측정 의미를 안내한다. (FR-008)
- [x] T009 `tests/`의 관련 기존 테스트와 새 테스트를 실행하고 명세 대비 수렴을 확인한다. (SC-001~004)

## 의존성과 구현 전략

T001 → T002 → T003 → T004/T005 → T006 → T007 → T008 → T009 순서로 수행한다. T004와 T005는 기반 완료 후 서로 다른 파일에서 병렬 수행 가능하나 이번 구현은 순차 수행한다. 최소 기능은 사용자 이야기 1이며 뒤이어 비동기 상태와 전체 검증을 완료한다. 사용자 이야기 1은 알려진 구간별 시간, 사용자 이야기 2는 범위 격리와 상태 건수로 독립 검증한다.

## 검증 결과

새 감지 리포트 테스트 14개가 모두 통과했다. 실제 예제 YOLO·TensorRT 모델의 단일·배치 구간 분리, 공유 배치의 실행 격리, GPU 추가 동기화 금지, 타임아웃·부분 종료·바쁨·오류 상태를 확인했다.

전체 회귀 테스트는 223개 중 218개 통과, 3개 건너뜀, 2개 오류였다. 두 오류는 기존 examples/02_multiple_stream_rtsp_style.py가 존재하지 않는 step.post_process 모듈을 가져오는 문제이며 이번 변경 파일이 아니다. 단독 실행에서도 재현했다. Windows named pipe 통합 테스트는 샌드박스 밖에서 재실행하여 검증했다.
