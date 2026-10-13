# 작업 목록: Batch 실행 프로세스 선택

## 1단계: 준비
- [x] T001 specs/028-batch-process-routing/의 명세·설계와 .gitignore를 확인한다.

## 2단계: 기반 검증
- [x] T002 tests/test_pipeline_routing.py에 직접·중첩·혼합·PID·비직렬화 실행 테스트를 작성하고 실패를 확인한다. (FR-001~FR-003)

## 3단계: 사용자 이야기 1 - 일반 실행
- [x] T003 [US1] src/pipeworks/pipeline.py에서 Batch 없는 경우 기존 _run_local을 선택한다. (FR-001, FR-004)

## 4단계: 사용자 이야기 2 - 공유 Batch 실행
- [x] T004 [US2] src/pipeworks/pipeline.py에서 알려진 래퍼를 탐색하고 Batch 존재 시 기존 run_remote를 선택한다. (FR-002~FR-005)
- [x] T005 [US2] tests/test_central_process.py의 프로토콜 테스트를 명시적 중앙 실행으로 유지하고 Batch 그룹 선택을 검증한다. (FR-005)

## 5단계: 문서 및 검증
- [x] T006 README.md 및 현재 docs/site 실행 설명에 일반·Batch 실행 위치를 반영한다. (FR-001~FR-005)
- [x] T007 tests/의 라우팅·설정·중앙 실행·추론 회귀 검증을 실행하고 specs/028-batch-process-routing/quickstart.md에 결과를 기록한다. (SC-001~SC-003)

## 의존성과 실행 순서
T001 → T002 → T003 → T004 → T005 → T006 → T007. 먼저 일반 실행을 완성하고 공유 Batch 실행을 검증한다. 같은 파일 작업은 순차 실행한다.

## 병렬 가능 예시
사용자 이야기 1의 PID 검증과 사용자 이야기 2의 구성 사례 검토는 독립적으로 읽을 수 있다. 실제 구현과 테스트 수정은 단일 작업자가 순서대로 수행한다.

## 구현 전략
공통 실행기와 기존 추론 엔진을 재사용한다. 실행 위치 선택만 변경하고 문서·프로토콜 회귀 검증을 함께 완료한다.
