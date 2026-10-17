# 작업 목록: 배치 서버 옵션명 변경

## 1단계: 준비

- [x] T001 specs/045-batch-server/spec.md에 기존 명세를 참조하여 요구사항 및 명확화 검토를 기록한다.
- [x] T002 specs/045-batch-server/plan.md와 계약에 설계 및 제약을 기록한다.

## 2단계: 사용자 이야기 1

- [x] T003 [US1] pipeline.py와 main.py의 인자·속성·오류 메시지를 변경한다. (FR-001~FR-003)
- [x] T004 [US1] specs/045-batch-server/remaining.patch에 외부 파일 변경분을 준비한다. (FR-004)
- [x] T005 [US1] specs/045-batch-server/verify.py로 변경된 계약 및 기존 회귀를 검증한다. (SC-001~SC-002)
- [ ] T006 [US1] remaining.patch를 외부 원본 examples·docs·tests·관련 명세에 적용한다. (FR-004)

## 3단계: 마무리

- [x] T007 specs/045-batch-server/validation.md에 결과 및 남은 권한 제약을 기록한다.

## 의존성과 실행

T001 → T002 → T003 → T004 → T005 → T006 → T007 순서다.
T006은 쓰기 권한 제약으로 보류하되 독립적인 검증 결과 기록은 수행한다.

## 4단계: 수렴 후 남은 작업

- [ ] T008 외부 경로 쓰기가 가능한 환경에서 specs/045-batch-server/remaining.patch를 저장소 루트에 적용하고 원본 tests/ 회귀를 실행한다. FR-004의 부분 구현 해소이며 T006과 함께 완료한다.

