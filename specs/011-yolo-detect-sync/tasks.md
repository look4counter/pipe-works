# 작업 목록: 동기 GPU YOLO 감지

**명세**: [spec.md](spec.md)
**계획**: [plan.md](plan.md)

- [x] T001 모델 경로와 추론 옵션·간격 설정을 검증한다. (FR-001)
- [x] T002 모델을 재사용하며 선택 프레임을 동기 추론하는 기존 경로를 구현한다. GPU 전환은 T010에서 수행한다. (FR-002~FR-004)
- [x] T003 결과를 원래 컨텍스트에 연결하고 건너뜀과 오류에서도 순서를 유지한다. (FR-005, FR-006)
- [x] T004 실제 시작된 추론을 공통 보고 항목에 기록한다. (FR-007)
- [x] T005 간격, 설정, 오류 복구와 실제 모델 추론을 검증한다. (SC-001~SC-003)
- [x] T006 공통 보고 형식을 검증한다. (SC-004)

## 1단계: 준비

- [x] T007 `.specify/feature.json`과 `specs/011-yolo-detect-sync/checklists/requirements.md`의 활성 기능·명세 품질을 확인한다.

## 2단계: 기반

- [x] T008 `src/pipeworks/local_yolo.py`와 설치된 예측기의 GPU 경로 및 `.gitignore`를 확인한다.

## 3단계: US1 CPU 복사 없는 단일 감지

독립 검증: CPU 복사 호출을 차단해도 단일 프레임의 원본 좌표와 CUDA 결과가 전달되어야 한다.

- [x] T009 [US1] `tests/test_yolo_detect.py`의 기존 CPU 결과 계약을 CUDA 계약으로 갱신하고 복사 금지·좌표 복원·잘못된 입력 검증을 추가한다. (FR-001~FR-009, SC-001~SC-006)
- [x] T010 [US1] `src/pipeworks/embedded/yolo_detect.py`에 GPU 입력 검증·변환·전용 예측기·좌표 복원·완료 동기화를 구현한다. (FR-003~FR-009)
- [x] T011 [US1] `tests/test_yolo_detect.py`, `tests/test_local_yolo.py`, `tests/test_yolo_detect_batch.py`로 단일·공유 GPU 경로를 검증한다. 실제 엔진 검증의 환경 제한은 `quickstart.md`에 기록한다. (SC-001~SC-006)

## 4단계: 문서와 수렴

- [x] T012 `docs/pipeworks/embedded/yolo_detect.md` 및 `README.md`에 GPU 영상·결과 계약을 반영한다. (FR-003, FR-008)
- [x] T013 `specs/011-yolo-detect-sync/quickstart.md`에 검증 결과를 기록하고 명세·계획·코드의 수렴을 확인한다.

## 의존성과 실행 전략

T007 → T008 → T009 → T010 → T011 → T012 → T013 순서로 수행한다. US1이 전체 요청의 최소 완성 범위다. T010 이후 T012 문서 작성과 T011 실행은 독립적이나 이번 작업에서는 순서대로 수행한다. 기존 완료 항목은 이전 기능의 기록이며 새 GPU 조건은 T009~T013에서 검증한다.

## 5단계: 비동기 전환 준비

- [x] T014 `specs/011-yolo-detect-sync/spec.md`와 설계 문서·품질 점검표의 비동기 조건, CUDA 수명 및 제한 시간 규칙을 확인한다. (FR-001~FR-014)

## 6단계: US1 지연·실패에도 영상 전달

독립 검증: 작업자 초기화·추론을 이벤트로 정지해도 제한 시간 이후 원본 영상이 계속 전달되고 요청·작업자 수가 1개로 제한되어야 한다.

- [x] T015 [US1] `tests/test_yolo_detect.py`에 제한 시간 파일·지연·초기화 실패·추론 실패·늦은 완료·종료·재실행·별도 CUDA 스트림·통계 귀속 검증을 추가하고 기존 GPU 검증을 비동기 계약에 맞춘다. (SC-001~SC-008)
- [x] T016 [US1] `src/pipeworks/embedded/yolo_detect.py`에 모델 동명 YAML, 1개 요청 슬롯, 데몬 작업자, GPU 복제·이벤트·전용 스트림, 제한 시간 대기와 늦은 결과 폐기·종료를 구현한다. (FR-002~FR-014)
- [x] T017 [US1] `tests/test_yolo_detect.py`, `tests/test_yolo_detect_batch.py`, `tests/test_local_yolo.py`를 실행해 비동기와 공유 GPU 계약을 검증한다. (SC-001~SC-008)

## 7단계: 안내와 수렴

- [x] T018 `README.md`, `docs/pipeworks/embedded/yolo_detect.md`, `specs/011-yolo-detect-sync/quickstart.md`에 비동기 동작·동명 YAML·사용 중 건너뜀·늦은 결과 폐기 및 검증 결과를 반영한다. (FR-010~FR-014)
- [x] T019 `specs/011-yolo-detect-sync/tasks.md`와 현재 코드를 수렴 점검하고 미완료 구현이 있으면 추가 작업으로 완료한다.

비동기 전환은 T014 → T015 → T016 → T017 → T018 → T019 순서로 수행한다. 이전 완료 항목은 동기식 구현의 기록이다. 현재 구현의 전체 완성 범위는 US1의 비동기 전환이며 예제 소스·공유 YAML의 사용자 변경은 수정 대상이 아니다.

## 8단계: 수렴 보완

- [x] T020 `src/pipeworks/embedded/yolo_detect.py`와 `tests/test_yolo_detect.py`에서 실패한 실제 추론의 실행 시간도 제출 문맥의 통계에 기록하고 검증한다. FR-007의 부분 충족을 보완한다.

## 9단계: 동기 처리 명세와 기반

앞선 완료 항목은 이전 구현의 이력이다. 현재 요구사항은 갱신한 명세·계획을 기준으로 T021 이후에서 검증한다.

- [x] T021 `specs/011-yolo-detect-sync/`의 명세·명확화·설계·계약과 작업 목록을 동기 처리로 갱신하고 일관성을 분석한다. (FR-001~FR-011)
- [x] T022 [US1] `tests/test_yolo_detect.py`에 동기 대기·호출 스레드·오류 전파·모델 재사용·GPU 결과·통계 테스트를 작성하여 구현 전 실패를 확인한다. (SC-001~SC-004)

## 10단계: US1 기본 동기 추론

독립 검증: 이벤트 차단 해제 전에는 프레임이 반환되지 않고 원본 객체와 GPU 결과를 유지해야 한다.

- [x] T023 [US1] `src/pipeworks/embedded/yolo_detect.py`에서 내부 작업자·요청·시간 제한과 오류 통과를 제거하고 호출 스레드의 동기 GPU 추론을 구현한다. (FR-001~FR-010)
- [x] T024 [US1] `src/pipeworks/embedded/tensor_rt_inference.py`의 슬롯 관리 메서드를 자체 작업자에 옮겨 YOLO 내부 클래스 의존성을 제거하고 기존 TensorRT 검증을 실행한다. (FR-011)

## 11단계: US2 선택적 비동기와 문서

독립 검증: 공통 Async로 감싼 모델은 지연·오류 시 원본을 통과시켜야 한다.

- [x] T025 [US2] `tests/test_yolo_detect.py`에서 공통 Async의 지연·오류·늦은 결과 격리와 통계 귀속을 검증한다. (FR-010, SC-005)
- [x] T026 [US2] `README.md`, `docs/pipeworks/embedded/yolo_detect.md`, `docs/pipeworks/embedded/async.md`에 동기 기본 동작과 선택적 조합을 반영한다. (FR-003, FR-006, FR-010)

## 12단계: 검증과 수렴

- [x] T027 `tests/`의 관련 GPU·배치·Async·TensorRT 회귀와 전체 검증을 실행하고 `specs/011-yolo-detect-sync/quickstart.md`에 결과를 기록한다.
- [x] T028 `specs/011-yolo-detect-sync/`의 현재 명세·계획·작업 대비 코드 수렴을 점검하고 남은 작업을 완료한다.

의존성: T021 → T022 → T023 → T024 → T025 → T026 → T027 → T028. T023·T024는 가져오기 의존성을 함께 바꾸므로 순차로 처리하되 두 파일을 모두 수정한 뒤 실행한다. 이후 문서 작성과 관련 회귀 실행은 독립적으로 수행할 수 있다.
