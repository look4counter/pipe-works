# 작업 목록: PatchCore 실행부

입력: [명세](spec.md), [계획](plan.md), 연구·데이터 모델·계약.

## 1단계: 준비

- [x] T001 specs/047-patchcore-backend/spec.md와 체크리스트의 범위·명확화 완료를 확인한다.

## 2단계: 기반

- [x] T002 tests/test_patchcore_backend.py에 기준 구현 비교·입력/파일 오류·GPU 통합 검증을 작성한다.

## 3단계: 사용자 이야기 1

- [x] T003 [US1] src/pipeworks/yolo_backends/patchcore.py에 체크포인트 검증·복원·동일 추론을 구현한다. FR-001/002/003/005/006.

## 4단계: 사용자 이야기 2

- [x] T004 [US2] src/pipeworks/backend.py와 src/pipeworks/yolo_backend.py에 enum·선택·매핑을 연결한다. FR-004.
- [x] T005 [US2] tests/test_patchcore_backend.py에서 단일·공유 배치 및 기존 실행부 회귀를 검증한다. SC-001/002/003.

## 5단계: 마무리

- [x] T006 docs/pipeworks/backend.md와 docs/pipeworks/yolo_backends/patchcore.md 및 목록을 갱신한다.
- [x] T007 specs/047-patchcore-backend/validation.md에 결과와 한계를 기록하고 구현 후 수렴을 점검한다.

## 의존성 및 구현 전략

T001 → T002 → T003 → T004 → T005 → T007. T006은 T004 이후 검증과 병행할 수 있다.
사용자 이야기 1의 최소 기능을 먼저 검증한 다음 이야기 2를 통합한다.
독립 검증은 기준 구현 비교와 요청별 배치 결과 비교이다.
