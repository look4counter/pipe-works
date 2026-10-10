# 작업 목록: 추론 입력의 CPU 대기 제거

입력: [명세](spec.md), [계획](plan.md). 최소 제공 범위는 사용자 이야기 1 전체이다.

## 1단계: 준비

- [x] T001 specs/022-cuda-input-wait/checklists/requirements.md와 실행 환경을 확인한다.

## 2단계: 기반 확인

- [x] T002 src/pipeworks/embedded/tensor_rt_inference.py와 src/pipeworks/local_tensor_rt.py의 입력 참조·오류 정리 경계를 확인한다. (FR-003, FR-004)

## 3단계: 사용자 이야기 1

목표: CPU 입력 대기 없이 준비 순서와 기존 결과 계약을 보장한다. 독립 검증: 지연된 GPU 입력 결과를 참조와 비교한다.

- [x] T003 [US1] tests/test_tensor_rt_inference.py에 같은·다른 스트림의 지연 입력 및 CPU 입력 대기 금지 회귀를 추가하고 기존 코드의 실패를 확인한다. (FR-001, FR-005)
- [x] T004 [US1] tests/test_local_tensor_rt.py에 복수 생산 스트림 배치의 지연 입력과 CPU 입력 대기 금지 회귀를 추가한다. (FR-002, FR-005)
- [x] T005 [US1] src/pipeworks/embedded/tensor_rt_inference.py에서 준비 이벤트를 반환하고 개별 소비 스트림에 연결하며 배치 중복 이벤트를 제거한다. (FR-001, FR-003)
- [x] T006 [US1] src/pipeworks/local_tensor_rt.py에서 입력 이벤트를 배치 소비 스트림에 연결한다. (FR-002, FR-003)

## 4단계: 검증과 문서

- [x] T007 docs/pipeworks/embedded/tensor_rt_inference.md의 입력 순서 보장 설명을 갱신한다. (FR-004)
- [x] T008 specs/022-cuda-input-wait/quickstart.md의 추론·배치·처리·비동기 회귀를 실행하고 결과를 기록한다. (SC-001, SC-002, SC-003)

## 의존성과 실행 전략

T001 → T002 → T003/T004 → T005/T006 → T007 → T008 순서로 수행한다. T003과 T004는 다른 테스트 파일이므로 병렬 가능하지만 이번에는 순차 수행한다. 구현도 순차 수행하여 검토한다. 완료 후 converge에서 명세·계획·코드의 차이를 확인한다.
