# 작업 목록: 단계별 YAML 설정과 동적 컨텍스트

**명세**: [spec.md](spec.md)
**계획**: [plan.md](plan.md)

- [x] T001 생성 시 YAML 최상위와 모든 단계 섹션을 검증하고 속성형 설정으로 보관한다. (FR-001, FR-002)
- [x] T002 `.step()` 등록 시 원래 클래스명 섹션을 `configure()`에 전달한다. (FR-002~FR-004)
- [x] T003 사용자 정의 단계의 재시작에 필요한 설정을 핫스왑 래퍼에 보관한다. (FR-005)
- [x] T004 고정 필드 없는 `PipelineContext`와 새 출력 컨텍스트의 계약을 구현한다. (FR-006, FR-007)
- [x] T005 RTSP 설정과 중앙 중단 이벤트를 적용하고 관련 설정·RTSP 테스트를 실행한다. (FR-008, SC-001~SC-003, SC-005)
- [x] T006 같은 객체를 전달하는 단계의 임의 속성 유지와 새 컨텍스트 생성 단계의 구분을 명시적으로 검증한다. (SC-004)

## 단계 2: 실행 중 설정 변경

- [x] T007 [US1] `tests/test_pipeline_config.py`에 사용자·내장 단계의 실행 중 설정 변경, 무관한 섹션 변경, 잘못된 YAML 복구를 검증한다. (FR-009~FR-011)
- [x] T008 [US1] `src/pipeworks/pipeline.py`에 설정 파일 감시와 단계별 설정 공급을 구현한다. (FR-009, FR-011)
- [x] T009 [US1] `src/pipeworks/hotswap.py`에 설정 변경 감지와 설정 실패 시 복구를 구현한다. (FR-010~FR-012)
- [x] T010 [US1] `src/pipeworks/pipeline.py`에서 내장 Step 실행 래퍼와 `Tap` 내부 Step의 설정 감시를 연결한다. (FR-010, FR-012)
- [x] T011 [US1] `tests/test_pipeline_config.py`와 `tests/test_central_process.py`에 소스·Tap·중앙 실행 설정 변경을 검증한다. (SC-006~SC-008)
- [x] T012 `tests/test_pipeline_context.py`에서 미완료 T006의 컨텍스트 계약을 검증하고 관련 전체 테스트를 실행한다. (SC-004, SC-006~SC-008)

## 의존성

- T007을 먼저 실행해 현재 동작의 실패를 확인한다. T008~T010은 순서대로 수행하고 T011과 T012로 검증한다.

## 단계 3: 설정만 바뀐 경우 영상 연결 유지

- [x] T013 [US1] `tests/test_pipeline_config.py`에서 설정 변경 전후 Step 인스턴스와 처리 반복자가 유지되는지 검증하고 현재 실패를 확인한다. (FR-010, SC-009)
- [x] T014 [US1] `src/pipeworks/hotswap.py`에서 기존 인스턴스에 `configure()`를 실행하고 오류 시 이전 최상위 속성을 복원한다. (FR-010, FR-011)
- [x] T015 [US1] `tests/test_pipeline_config.py`의 소스·Tap·내장 단계 기대값을 재시작 없는 동작에 맞게 갱신한다. (SC-006~SC-009)
- [x] T016 [US1] `tests/test_hotswap.py`에서 코드 변경과 설정 변경의 동시 적용 및 설정 오류 복구를 검증한다. (FR-011, FR-012)
- [x] T017 `tests/test_central_process.py`와 관련 전체 테스트를 실행하고 `specs/003-step-yaml-config/quickstart.md`와 동작을 비교한다. (SC-006~SC-009)

## 추가 의존성

- T013 실패를 확인한 뒤 T014를 구현한다. T015~T017은 T014 이후 수행한다.

## 단계 4: RTSP 제한 시간 밀리초 통일

- [x] T018 `specs/003-step-yaml-config/`의 명세·명확화·계획·작업과 RTSP 단위 계약의 일관성을 검토한다. (FR-013, FR-014)
- [x] T019 [US2] `tests/test_rtsp_source.py`, `tests/test_rtsp_publish.py`에 기본값·0·소수 밀리초의 변환, 이전 옵션·잘못된 값 거부 테스트를 작성하고 구현 전 실패를 확인한다. (SC-010, SC-011)
- [x] T020 [US2] `src/pipeworks/embedded/rtsp_source.py`, `src/pipeworks/embedded/rtsp_publish.py`에 `timeout_ms` 기본값·검증과 라이브러리 단위 변환을 구현한다. (FR-013, FR-014)
- [x] T021 [US2] `examples/config/stream.yml`, `README.md`, `docs/pipeworks/pipeline.md`, `docs/pipeworks/embedded/rtsp_source.md`, `docs/pipeworks/embedded/rtsp_publish.md` 및 `specs/002-rtsp-packet-source/`, `specs/004-rtsp-publish/`의 제한 시간 계약을 갱신한다. (FR-014, SC-011)
- [x] T022 `tests/test_pipeline_config.py`와 관련 RTSP·전체 회귀 검증을 실행하고 `specs/003-step-yaml-config/quickstart.md`에 결과를 기록한 뒤 수렴 점검을 완료한다. (SC-010, SC-011)

T018 → T019 → T020 → T021 → T022 순서로 수행한다. 기존 사용자 변경을 보존하고 모델 YAML과 재연결 간격은 변경하지 않는다. 독립 검증은 두 RTSP 단계가 같은 밀리초 설정을 각각 올바른 연결 값으로 전달하는지 확인한다.

## 단계 5: 재연결 간격 밀리초 통일

- [x] T023 명세·명확화·계획·데이터 계약을 갱신하고 일관성을 분석한다. (FR-015, FR-016)
- [x] T024 tests/test_rtsp_source.py와 test_rtsp_publish.py에 대기 단위·중단·재시도 경계·설정 오류 검증을 추가한다. (SC-012, SC-013)
- [x] T025 두 RTSP 소스 파일의 설정 이름·기본값·검증·대기 환산과 로그를 수정한다. (FR-015, FR-016)
- [x] T026 예제 YAML·README·공개 문서와 관련 데이터 계약을 갱신하고 RTSP·파이프라인 구성 테스트를 실행한다. (SC-013)
- [x] T027 검증 결과를 quickstart에 기록하고 수렴 점검으로 남은 작업을 확인한다. (FR-015, FR-016, SC-012, SC-013)

T023 → T024 → T025 → T026 → T027 순서로 수행한다.
