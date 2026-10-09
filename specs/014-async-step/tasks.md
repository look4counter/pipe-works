# 작업 목록: 공통 Async 단계

**입력**: [명세](spec.md), [계획](plan.md), [계약](contracts/async.md)

## 단계 1: 준비

- [x] T001 `specs/014-async-step/`의 명세·명확화·계획·계약·작업 목록 일관성을 확인한다.

## 단계 2: 기반

- [x] T002 `tests/test_async.py`에 설정, 원본 식별, 성공·지연·사용 중·실패 계약 테스트를 작성하고 구현 전 실패를 확인한다.

## 단계 3: 사용자 이야기 1 — 대기 제한

독립 검증: 일반 처리 단계에서 성공 결과와 원본 통과, 입력 순서를 확인한다.

- [x] T003 [US1] `src/pipeworks/embedded/async_step.py`에 지속 입력 슬롯과 한 요청 제한, 기한 판정, 오류 복구를 구현한다. (FR-001~FR-005, FR-009)
- [x] T004 [US1] `src/pipeworks/embedded/__init__.py`에 공개 가져오기를 추가하고 `async_step.py`의 설정 전달을 검증한다. (FR-002, FR-010)

## 단계 4: 사용자 이야기 2 — 격리와 수명

독립 검증: 중첩 데이터와 텐서, 상태 유지와 종료를 확인한다.

- [x] T005 [US2] `tests/test_async.py`에 상태 유지, 실행 문맥, 중첩 데이터·텐서 격리, 계약 위반, 차단 종료, GPU 검증을 추가한다. (FR-006~FR-009, SC-001~SC-003)
- [x] T006 [US2] `src/pipeworks/embedded/async_step.py`에 안전한 입력 복사와 GPU 소유권 보관, 실행 문맥 전달, 작업자 종료 정리를 구현한다. (FR-006~FR-008)

## 단계 5: 마무리

- [x] T007 [P] `docs/pipeworks/embedded/async.md`에 사용법·설정·지원 계약과 기존 모델과의 조합 한계를 작성한다. (FR-010)
- [x] T008 `README.md`에 Async 안내와 문서 링크를 추가한다. (FR-010)
- [x] T009 `tests/test_async.py`의 집중 검증과 전체 `tests/` 회귀 검증을 실행하고 `specs/014-async-step/` 산출물 대비 수렴 점검을 수행한다.

## 의존성과 구현 전략

T001 → T002 → T003 → T004 → T005 → T006 → T007·T008 → T009 순서로 수행한다. T007은 구현 안정화 후 문서 검토와 병렬 수행할 수 있다. 먼저 사용자 이야기 1의 최소 기능을 검증하고 이어서 격리와 자원 수명 요구를 검증한다. 동일 소스 파일 수정은 순차로 수행한다.

## 단계 6: 파이프라인 통합 보완

- [x] T010 `src/pipeworks/main.py`에서 Async 하위 사용자 단계의 직렬화를 등록하고, `src/pipeworks/embedded/async_step.py`에서 작업자 출력을 호출자에게 전달한다. `tests/test_async.py`에 파이프라인 구성과 직렬화·출력 전달 검증을 추가한다. (FR-006, FR-010)

T010은 전체 검증에서 확인한 통합 경로를 보완하며, 완료 후 T009의 검증과 수렴 점검을 다시 수행한다.

## 단계 7: 수렴 보완

- [x] T011 `src/pipeworks/embedded/async_step.py`에서 같은 인스턴스의 여러 처리 스트림이 작업자를 중복 실행하지 못하도록 실행 소유권을 제한한다. 종료된 스트림의 작업이 완료될 때까지 새 입력은 통과시키며 중앙 직렬화를 유지한다. `tests/test_async.py`에 종료 후 재사용과 직렬화 검증을 추가한다. (FR-005, FR-008, FR-010 부분 충족)

## 단계 8: 모듈 파일명 변경

- [x] T012 `specs/014-async-step/`에 파일명 변경 요구를 명세·명확화·계획·작업으로 반영하고 일관성을 분석한다. (FR-011)
- [x] T013 구현 파일명을 `src/pipeworks/embedded/async_step.py`로 변경하고 `__init__.py`, `tests/test_async.py`, `tests/test_yolo_detect.py`, `docs/pipeworks/embedded/async.md` 및 현재 설계 경로를 갱신한다. (FR-011)
- [x] T014 `tests/test_async.py`, `tests/test_yolo_detect.py`의 가져오기·직렬화·로그·동작 회귀를 실행하고 `specs/014-async-step/` 대비 수렴 점검을 완료한다. (FR-011)

T012 → T013 → T014 순서로 수행한다. 이전 작업 경로는 현재 파일명으로 정규화하며 클래스와 실행 로직은 변경하지 않는다.

## 단계 9: 타임아웃에만 입력 복사

- [x] T015 명세·명확화·계획·계약을 읽기 전용 공유 입력과 타임아웃 복사 정책으로 갱신하고 일관성을 분석한다. (FR-004, FR-007, FR-012)
- [x] T016 `tests/test_async.py`에서 정상 경로 무복사와 타임아웃 후 전달용 복사·원본 수명·경합·실패 계약을 검증하도록 수정하고 구현 전 실패를 확인한다. (FR-007, FR-012)
- [x] T017 `src/pipeworks/embedded/async_step.py`에서 얕은 작업 컨텍스트와 수명 보관, 타임아웃 복사·CUDA 완료·복사 실패 복구를 구현한다. (FR-004, FR-007, FR-012)
- [x] T018 `docs/pipeworks/embedded/async.md`, README와 설계 자료를 최신 계약으로 갱신하고 Async·YoloDetect 및 전체 회귀 검증 후 수렴 점검한다. (FR-010, SC-001~SC-003)

T015 → T016 → T017 → T018 순서로 수행한다. 모델 코드는 변경하지 않는다.
