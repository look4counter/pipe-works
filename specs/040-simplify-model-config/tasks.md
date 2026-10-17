# 작업 목록: 모델 배치 설정 단순화

## 1단계: 준비

- [X] T001 src/, examples/model/, tests/, docs/의 모델 설정 사용처를 확인한다. (FR-001~FR-005)

## 2단계: 사용자 이야기 1

- [X] T002 [US1] tests/test_explicit_model_config.py에 새 키·이전 키 및 범위 검증을 작성한다. (SC-001)
- [X] T003 [US1] src/pipeworks/의 모델 배치 키를 교체하고 외부 플러그인 경로를 제거한다. (FR-001~FR-004)
- [X] T004 [US1] examples/model/, tests/, README.md와 docs/의 계약을 갱신한다. (FR-005)

## 3단계: 최종 검증

- [X] T005 관련 tests/를 실행하고 소스 검색과 명세 대조로 누락을 확인한다. (SC-001~SC-003)

## 의존성과 전략

T001 → T002 → T003 → T004 → T005 순서다. 문서와 테스트 파일은 병렬 편집 가능하지만 이번에는 순차 진행한다. 최소 완성 범위는 사용자 이야기 1 전체다.


## 4단계: 명칭 확정 반영

- [X] T006 [US1] src/, tests/, examples/model/, README.md와 docs/의 배치 대기 키를 max_batch_wait_ms로 통일하고 이전 batch_timeout_ms 오류 처리를 검증한다. (FR-001, FR-004, FR-005, SC-001)
- [X] T007 관련 설정·수집기·GPU 배치·중앙 실행 테스트와 잔여 검색으로 변경을 검증한다. (SC-001, SC-003)

T006은 갱신 명세·계획의 일관성 확인 후 수행하고 T007은 T006에 의존한다. 이름과 의미만 정리하며 스케줄링 동작은 변경하지 않는다.

