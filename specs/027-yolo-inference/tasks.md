# 작업 목록: YOLO 추론 단계 분리

**입력**: [명세](spec.md), [계획](plan.md), [계약](contracts/yolo-inference.md)

## 단계 1: 준비

- [x] T001 specs/027-yolo-inference/plan.md의 로컬 API 조사와 기존 코드 보존 범위를 확인한다.

## 단계 2: 기반

- [x] T002 specs/027-yolo-inference/contracts/yolo-inference.md의 입력·출력·배치 계약과 .gitignore를 확인한다.

## 단계 3: 사용자 이야기 1 - 추론 전용 단계

**독립 검증**: 원시 출력 전달, 설정, 건너뜀, 잘못된 입력과 오류 전파를 확인한다.

- [x] T003 [US1] tests/test_yolo_inference.py에 설정·간격·원시 출력·오류 계약 테스트를 작성하고 구현 전 실패를 확인한다. (FR-001~004, FR-007)
- [x] T004 [US1] src/pipeworks/embedded/yolo_inference.py에 원시 세션과 설정·GPU 검증·완료 정리·보고를 구현한다. (FR-001~004)
- [x] T005 [US1] src/pipeworks/embedded/__init__.py에 YoloInference를 공개한다. (FR-001)

## 단계 4: 사용자 이야기 2 - 공유 실행과 호환성

**독립 검증**: 호환 배치 결합과 결과 분리, 실패 후 복구, 기존 감지와 비동기 보고 호환성을 확인한다.

- [x] T006 [US2] tests/test_yolo_inference.py에 공유 배치·결과 소유권·실패·GPU 검증 테스트를 추가한다. (FR-004~007)
- [x] T007 [US2] src/pipeworks/local_yolo_inference.py에 공유 배치 워커와 요청별 결과 복제를 구현한다. (FR-005)
- [x] T008 [US2] src/pipeworks/embedded/cuda_async.py에서 새 추론 단계를 YOLO 보고 대상으로 인식한다. (FR-006)

## 단계 5: 문서와 검증

- [x] T009 docs/pipeworks/embedded/yolo_inference.md와 README.md에 전후처리 연결·설정·배치·제약을 한글로 기록한다. (FR-007, SC-003)
- [x] T010 tests/test_yolo_inference.py와 기존 전체 테스트를 실행하고 specs/027-yolo-inference/quickstart.md에 결과를 기록한다. (SC-001~002)

## 단계 6: 추가 준비와 기반

- [x] T011 specs/027-yolo-inference/spec.md와 plan.md의 추가 전후처리 계약 및 기존 사용자 예제 변경을 확인한다.
- [x] T012 specs/027-yolo-inference/checklists/requirements.md를 재검증하고 명세·계획·작업의 요구사항 연결을 분석한다.

## 단계 7: 사용자 이야기 3 - YOLO 전후처리와 전체 보고

**독립 검증**: GPU 이미지부터 모델별 감지 결과를 만들고 세 구간을 YOLO 완료 표본 하나로 기록한다.

- [x] T013 [US3] tests/test_yolo_processing.py에 설정·GPU 변환·NMS·좌표 복원·오류·보고 계약 테스트를 작성하고 구현 전 실패를 확인한다. (FR-008~011, SC-004)
- [x] T014 [US3] examples/step/yolo_pre_process.py에 GPU 전처리와 프레임 해제·좌표 변환·YOLO 프로파일 생성을 구현한다. (FR-008, FR-010~011)
- [x] T015 [US3] examples/step/yolo_post_process.py에 설정 검증·GPU NMS·좌표 복원·모델별 결과 저장·임시 정리를 구현한다. (FR-009~011)
- [x] T016 [US3] src/pipeworks/embedded/yolo_inference.py에서 상속 YOLO 프로파일과 완료 위임·건너뜀을 연결한다. (FR-011)
- [x] T017 [US3] src/pipeworks/embedded/cuda_async.py에 YOLO 전후처리 인식과 프로파일 부분 종료 정리를 연결한다. (FR-011)
- [x] T018 [US3] examples/01_single_stream_rtsp_style.py의 새 단계 import와 YOLO 보고 연결을 완성한다. (FR-012)

## 단계 8: 추가 문서와 검증

- [x] T019 docs/pipeworks/embedded/yolo_inference.md 및 README.md에 YOLO 전후처리 옵션과 전체 보고 연결을 기록한다. (FR-007, SC-003)
- [x] T020 tests/test_yolo_processing.py, tests/test_yolo_inference.py 및 기존 TensorRT·비동기·보고 회귀를 실행하고 specs/027-yolo-inference/quickstart.md에 검증 결과를 기록한다. (SC-002, SC-004)

## 추가 작업의 의존성

## 단계 10: 공통 계약 준비와 기반

- [x] T025 specs/027-yolo-inference/spec.md, plan.md, research.md, data-model.md, contracts/yolo-inference.md에 공통 입출력·좌표·보고·기본값을 반영하고 명확화·체크리스트·분석을 완료한다. (FR-014~017)
- [x] T026 [US4] tests/test_inference_contract.py에 교차 전후처리·named input·공통 좌표·보고·이전 입력 정리 계약 테스트를 작성하고 구현 전 실패를 확인한다. (SC-006)
- [x] T027 [US4] src/pipeworks/inference_contract.py에 좌표/프로파일 조회·실제 백엔드 바인딩·공통 임시 정리를 구현한다. (FR-014, FR-016~017)

## 단계 11: 사용자 이야기 4 - 추론만 교체

- [x] T028 [US4] src/pipeworks/image_preprocessing.py와 examples/step/yolo_pre_process.py 및 tensor_rt_pre_process.py에 Step 직접 상속을 유지하는 동일 전처리 구현·옵션·image_transform을 연결한다. (FR-013~015)
- [x] T029 [US4] src/pipeworks/detection_postprocessing.py와 examples/step/yolo_post_process.py 및 tensor_rt_post_process.py에 동일 후처리 구현·기본값·FP16·names·end2end·cleanup을 연결한다. (FR-015, FR-017)
- [x] T030 [US4] src/pipeworks/embedded/yolo_inference.py 및 tensor_rt_inference.py에 공통 프로파일 바인딩을 연결하고 YOLO named 단일 입력을 지원한다. (FR-014, FR-016)
- [x] T031 [US4] src/pipeworks/embedded/cuda_async.py에 공통 프로파일 종료 및 실제 추론 백엔드 우선 상태 분류를 연결한다. (FR-016)

## 단계 12: 공통 계약 문서와 검증

- [x] T032 tests/test_yolo_processing.py, tests/test_tensor_rt_preprocess.py, tests/test_tensor_rt_processing.py, tests/test_tensor_rt_postprocess_optimized.py 등 관련 검증을 공통 필드·기본값에 맞게 갱신하고 docs/pipeworks/embedded 및 README.md에 교체 계약과 이전 입력 호환을 기록한다. (FR-014~017, SC-003)
- [x] T033 tests/test_inference_contract.py와 관련 GPU·추론·배치·비동기·보고 회귀를 실행하고 specs/027-yolo-inference/quickstart.md에 결과를 기록한다. (SC-002, SC-004~006)

T025 → T026 → T027 → T028 → T029 → T030 → T031 → T032 → T033 순서다. 각 예제는 Step 직접 상속을 유지하고 기존 완료 작업과 사용자 변경은 보존한다. 두 전처리/후처리의 구성·결과 검증은 독립적으로 실행할 수 있고 백엔드 보고 검증은 통합 뒤에 실행한다.

## 단계 9: Step 직접 상속

- [x] T021 specs/027-yolo-inference/spec.md와 plan.md에 직접 상속·독립성·기존 계약 유지 요구를 명세하고 명확화·설계·체크리스트 및 일관성 분석을 완료한다. (FR-013)
- [x] T022 [US3] tests/test_yolo_processing.py에서 TensorRT 전처리 모듈을 차단한 가져오기·Step 직접 상속 검증을 추가하고 구현 전 실패를 확인한다. (FR-013, SC-005)
- [x] T023 [US3] examples/step/yolo_pre_process.py를 Step 직접 상속으로 바꾸고 설정 검증·GPU 변환 도우미를 자체 구현한다. (FR-008, FR-010~011, FR-013)
- [x] T024 docs/pipeworks/embedded/yolo_inference.md와 specs/027-yolo-inference/quickstart.md에 독립 단계와 검증 결과를 기록하고 tests/test_yolo_processing.py 및 tests/test_yolo_inference.py 회귀를 실행한다. (SC-004~005)

T021 → T022 → T023 → T024 순서로 수행하며 기존 완료 작업은 보존한다. 구현 후 수렴 검토로 남은 요구사항을 확인한다.

T011 → T012 → T013 → T014 → T015 → T016 → T017 → T018 → T019 → T020 순서다. 기존 T001~T010은 완료 상태를 보존한다. 전처리와 후처리의 독립 테스트는 나눠 검증할 수 있으나 전체 보고는 추론·비동기 연결 뒤에 검증한다.

## 기존 작업의 의존성과 병렬 기회

T001 → T002 → T003 → T004 → T005 → T006 → T007 → T008 → T009 → T010 순서로 수행한다. 사용자 이야기 2는 이야기 1의 세션을 사용한다. 이야기 1의 설정/흐름 검증과 이야기 2의 배치/호환 검증은 각각 독립적인 검증 항목이다. 구현 완료 후 문서 검토와 테스트 실행을 별도로 진행할 수 있으나 동일 파일 변경은 순차 처리한다.

## 구현 전략

먼저 개별 원시 추론을 검증 가능한 최소 기능으로 만들고 공유 배치와 보고 연동을 더한다. 모든 작업은 체크박스·ID·파일 경로를 가지며 이야기 단계에는 US 표시가 있다. 구현 후 speckit-converge로 전체 의도를 검토한다.

## 단계 13: GPU 전용 범용화 준비와 기반

- [x] T034 specs/027-yolo-inference/spec.md·plan.md·research.md·data-model.md·contracts/yolo-inference.md의 GPU 전용 계약을 갱신하고 명확화·체크리스트·분석을 완료한다. (FR-018~024)
- [x] T035 [US5] tests/test_yolo_gpu_backends.py에 라이브러리 차단·다중 입출력·중첩 출력·CPU 전환·공유 배치 계약 테스트를 작성하고 구현 전 실패를 확인한다. (SC-007~009)

## 단계 14: 사용자 이야기 5 - GPU 전용 실행부

- [x] T036 [US5] src/pipeworks/yolo_backend.py에 실행부 선택·GPU 입력/출력·연산 감시·서명·배치 설정 계약을 구현한다. (FR-018~022)
- [x] T037 [US5] src/pipeworks/yolo_backends/torchscript.py·ultralytics.py·__init__.py에 기본 라이브러리 독립 실행과 명시적 호환 실행을 구현한다. (FR-018~021, FR-023)
- [x] T038 [US5] src/pipeworks/embedded/yolo_inference.py에 backend 설정·다중 입력·모든 출력·GPU 전용 세션을 연결한다. (FR-018~021, FR-024)
- [x] T039 [US5] src/pipeworks/local_yolo_inference.py에 실행부별 캐시·다중 입력 결합·모든 출력 배치 축 검증·실패 후 복구를 연결한다. (FR-022)

## 단계 15: 범용화 문서와 검증

- [x] T040 examples/config/stream.yml·docs/pipeworks/embedded/yolo_inference.md·README.md에 기존 모델의 명시적 어댑터와 새 GPU 계약·확장 방법을 기록한다. (FR-023)
- [x] T041 tests/test_yolo_inference.py·tests/test_inference_contract.py 등 관련 테스트를 새 계약에 맞추고 실제 GPU 및 회귀 검증을 실행하여 specs/027-yolo-inference/quickstart.md에 결과를 기록한다. (FR-024, SC-007~009)

T034 → T035 → T036 → T037 → T038 → T039 → T040 → T041 순서로 진행한다. 먼저 기본 GPU 단일·다중 입력 실행을 완성하고 공유 배치와 기존 감지 호환을 확인한다. T037의 두 어댑터는 서로 다른 파일이므로 독립 작성 가능하지만 이번 구현은 순차로 진행한다. 기존 완료 작업과 사용자 변경은 보존한다.

## 단계 16: Backend 선택 준비

- [x] T042 specs/027-yolo-inference/spec.md·plan.md·research.md·data-model.md·contracts/yolo-inference.md를 갱신하고 명확화 및 체크리스트를 검토한다. (FR-025~028)

## 단계 17: 사용자 이야기 6 - 필수 enum 선택

- [x] T043 [US6] tests/test_yolo_inference.py에 공개 enum·필수 인자·YAML 정규화와 복원 테스트를 작성하고 구현 전 실패를 확인한다. (SC-010)
- [x] T044 [US6] src/pipeworks/backend.py·__init__.py·embedded/__init__.py 및 embedded/yolo_inference.py에 공개 enum과 필수 인자·설정 정규화를 구현한다. (FR-025~027)
- [x] T045 [US6] examples/01_single_stream_rtsp_style.py와 관련 tests의 호출에 enum 선택을 명시한다. (FR-028)

## 단계 18: 문서와 회귀 검증

- [x] T046 README.md·docs/pipeworks/embedded/yolo_inference.md와 관련 안내에 필수 선택 사용법을 반영한다. (FR-028)
- [x] T047 관련 추론·설정·GPU·교차 계약 테스트를 실행하고 specs/027-yolo-inference/quickstart.md에 결과를 기록한다. (SC-010)

T042 → T043 → T044 → T045 → T046 → T047 순서로 실행한다. 관련 회귀 검증은 독립적으로 실행할 수 있으며 새 공개 계약을 먼저 완성하고 호출부와 안내를 갱신한다.


## 단계 19: 통합 준비

- [x] T048 specs/027-yolo-inference/spec.md·plan.md·research.md·data-model.md·contracts/yolo-inference.md에 통합 계약과 명확화 검토를 기록한다. (FR-029~033)

## 단계 20: 사용자 이야기 7 - TensorRT 선택

- [x] T049 [US7] tests/test_yolo_tensor_rt.py에 enum·설정·개별/공유 실행·보고·비동기 계약 테스트를 작성하고 구현 전 실패를 확인한다. (SC-011)
- [x] T050 [US7] src/pipeworks/backend.py와 yolo_backends/tensorrt.py에 TensorRT 선택 및 엔진 도우미를 제공한다. (FR-029~030)
- [x] T051 [US7] src/pipeworks/embedded/yolo_inference.py에 TensorRT 설정·실행·보고·정리를 통합하고 tensor_rt_inference.py를 호환 생성자 래퍼로 줄인다. (FR-030~033)
- [x] T052 [US7] src/pipeworks/local_tensor_rt.py의 엔진 가져오기와 embedded/cuda_async.py의 실제 backend 보고 분류를 갱신한다. (FR-031~032)

## 단계 21: 안내와 회귀

- [x] T053 examples/01_single_stream_rtsp_style.py·examples/config/stream.yml·README.md·docs/pipeworks/embedded/yolo_inference.md 및 tensor_rt_inference.md에 통합 사용법을 기록한다. (FR-033)
- [x] T054 관련 tests의 내부 patch 경로를 갱신하고 추론·설정·배치·보고·비동기 GPU 회귀를 실행하여 specs/027-yolo-inference/quickstart.md에 결과를 기록한다. (SC-011)

T048 → T049 → T050 → T051 → T052 → T053 → T054 순서로 진행한다. 관련 회귀 파일은 독립 실행 가능하나 GPU 검증은 자원 충돌을 피하도록 순차 실행한다. 먼저 새 공개 API를 검증하고 엔진·실행·보고를 연결한 뒤 기존 호환성을 확인한다.


## 단계 22: 제거 준비

- [x] T055 specs/027-yolo-inference/spec.md·plan.md·research.md·data-model.md·contracts/yolo-inference.md에 삭제 범위·명확화·설계를 기록한다. (FR-034~036)

## 단계 23: 사용자 이야기 8 - 통합 API만 유지

- [x] T056 [US8] tests/test_yolo_tensor_rt.py에 공개 export와 이전 모듈 부재 검증을 추가하고 구현 전 실패를 확인한다. (SC-012)
- [x] T057 [US8] src/pipeworks/embedded/tensor_rt_inference.py·__init__.py·cuda_async.py에서 이전 클래스·export·분류를 제거하고 yolo_backends/tensorrt.py의 설정 안내를 갱신한다. (FR-034~035)
- [x] T058 [US8] tests/test_tensor_rt_inference.py·test_tensor_rt_model_ids.py·test_step_config_defaults.py·test_detection_report.py·test_inference_contract.py의 호출·설정·내부 가져오기를 통합 API로 이관한다. (FR-035~036)

## 단계 24: 안내와 검증

- [x] T059 README.md·docs/pipeworks·docs/reference의 호출·설정·Step 이름·backend 안내를 통합 API로 갱신한다. (FR-035)
- [x] T060 관련 GPU·배치·설정·보고·비동기·레퍼런스 테스트를 실행하고 specs/027-yolo-inference/quickstart.md에 결과를 기록한다. (SC-012)

T055 → T056 → T057 → T058 → T059 → T060 순서로 수행한다. 서로 다른 안내 문서는 독립적으로 갱신 가능하나 이번 작업은 순차로 수행한다. 최소 삭제 계약을 먼저 검증하고 모든 호출과 안내를 이관한 후 GPU 회귀와 수렴을 확인한다.


## 단계 25: 공통 보고 준비

- [x] T061 specs/027-yolo-inference/spec.md·plan.md·research.md·data-model.md·contracts/yolo-inference.md에 통합·삭제·backend 분류 계약과 명확화를 기록한다. (FR-037~041)

## 단계 26: 사용자 이야기 9 - 하나의 보고 단계

- [x] T062 [US9] tests/test_detection_report.py에 삭제 부재·모든 backend 활성화·혼합 표본 분리 출력 검증을 추가하고 구현 전 실패를 확인한다. (SC-013)
- [x] T063 [US9] src/pipeworks/embedded/yolo_detect_report.py·stream_report.py·inference_contract.py에 공통 활성화·종류별 출력·단일 저장소·프로파일 연결을 구현한다. (FR-037~040)
- [x] T064 [US9] embedded/yolo_inference.py·cuda_async.py·local_yolo_inference.py·local_tensor_rt.py·yolo_backends/tensorrt.py의 측정을 공통 보고로 옮기고 embedded/tensor_rt_report.py와 공개 export를 삭제한다. (FR-037~040)
- [x] T065 [US9] 관련 tests의 가져오기·활성화·backend별 검증을 통합 계약에 맞게 갱신한다. (FR-039~041)

## 단계 27: 안내와 검증

- [x] T066 examples/01_single_stream_rtsp_style.py·README.md·docs/pipeworks/embedded의 보고 연결을 공통 API로 갱신한다. (FR-041)
- [x] T067 관련 GPU·공유 배치·전후처리·비동기·보고 회귀와 문서 예제를 검증하고 specs/027-yolo-inference/quickstart.md에 결과를 기록한다. (SC-013)

T061 → T062 → T063 → T064 → T065 → T066 → T067 순서다. 독립 문서와 테스트 파일 검토는 분리 가능하나 GPU 회귀는 순차 실행한다. 삭제·혼합 보고 계약을 먼저 검증하고 모든 실행 경로의 측정을 옮긴 뒤 수렴을 확인한다.

## 단계 28: 명칭 변경 준비

- [x] T068 specs/027-yolo-inference/spec.md·plan.md·research.md·data-model.md·contracts/yolo-inference.md에 새 이름·모듈·호환 정책을 기록하고 명확화·체크리스트·분석을 완료한다. (FR-042~044)

## 단계 29: 사용자 이야기 10 - YoloReport 연결

- [x] T069 [US10] tests/test_detection_report.py의 기존 공개 클래스 확인을 YoloReport로 갱신하고 구현 전 실패를 확인한다. (SC-014)
- [x] T070 [US10] src/pipeworks/embedded/yolo_detect_report.py를 yolo_report.py로 옮기고 클래스·ContextVar·export 및 src의 모든 보고 가져오기를 갱신한다. (FR-042~044)
- [x] T071 [US10] tests·examples·README.md·docs의 호출·가져오기·patch 경로를 YoloReport와 yolo_report로 갱신한다. (FR-043)

## 단계 30: 검증

- [x] T072 기존 보고·실제 GPU 추론·배치·전후처리·비동기 회귀와 문서 구문 및 이전 실행 의존성 부재를 확인하고 specs/027-yolo-inference/quickstart.md에 결과를 기록한다. (SC-014)

T068 → T069 → T070 → T071 → T072 순서다. 파일별 참조 확인은 독립적이지만 이번 작업은 순차 실행한다. 기존 구현 논리를 유지하며 새 공개 이름과 전체 연결을 검증한 뒤 수렴을 확인한다.

## 단계 31: 중앙 검증 준비

- [x] T073 specs/027-yolo-inference/spec.md·plan.md·research.md·data-model.md·contracts/yolo-inference.md에 세 backend의 실제 중앙 배치 계약을 기록하고 명확화·체크리스트·분석을 완료한다. (FR-045~048)

## 단계 32: 사용자 이야기 11 - 실제 중앙 배치

- [x] T074 [US11] tests/test_central_yolo_inference.py에 실제 모델 fixture·중앙 GPU Source·준비 동기화·실제 infer 관찰·GPU 결과 Sink를 작성한다. (FR-045~047)
- [x] T075 [US11] tests/test_central_yolo_inference.py에 세 backend별 Pipeline.run·CudaAsync·YoloReport·두 파이프라인·두 라운드 검증을 작성하고 실행한다. (FR-045~048)

## 단계 33: 결과 확인

- [x] T076 실제 세 backend 검증과 기존 배치·보고 회귀를 실행하고 specs/027-yolo-inference/quickstart.md에 PID·배치·세션·GPU 출력·보고 결과를 기록한다. (SC-015)

T073 → T074 → T075 → T076 순서로 수행한다. 모델 생성과 테스트별 결과 검토는 독립적이나 실제 GPU 검증은 순차 실행한다. 중앙 IPC나 모델 실행을 모의 구현으로 대체하지 않으며 테스트 후 수렴을 확인한다.

## 단계 34: 통합 준비

- [x] T077 specs/027-yolo-inference/spec.md·plan.md·research.md·data-model.md·contracts/yolo-inference.md에 통합 요구와 설계·명확화를 기록한다. (FR-049~052)

## 단계 35: 사용자 이야기 12 - 단일 공유 워커

- [x] T078 [US12] tests/test_local_yolo.py·test_local_tensor_rt.py·test_central_yolo_inference.py 등 관련 테스트의 경로와 명시적인 backend를 이관하고 이전 모듈 부재 및 공통 워커 계약을 검증한다. (SC-016)
- [x] T079 [US12] src/pipeworks/local_yolo_inference.py에 TensorRT 설정·profile별 세션·감지 세션·공통 수집·완료·오류·정리를 통합한다. (FR-049~051)
- [x] T080 [US12] src/pipeworks/embedded/yolo_inference.py·yolo_detect.py의 호출을 통합 모듈로 옮기고 src/pipeworks/local_tensor_rt.py·local_yolo.py를 삭제한다. (FR-049, FR-052)

## 단계 36: 안내와 검증

- [x] T081 README.md·docs의 현행 안내를 갱신하고 관련 GPU 감지·TensorRT 옵션·복구·보고·세 backend 중앙 배치 회귀를 실행하여 specs/027-yolo-inference/quickstart.md에 기록한다. (SC-016)

T077 → T078 → T079 → T080 → T081 순서로 수행한다. 독립 테스트 경로의 이관은 파일별로 가능하나 공유 파일 변경과 GPU 실행은 순차 수행한다. 기존 공개 API를 유지하는 통합을 먼저 완성하고 관련 실동작 검증 후 수렴을 점검한다.

## 단계 37: 예제 경계 준비

- [x] T082 specs/027-yolo-inference/spec.md·plan.md·research.md·data-model.md·contracts/yolo-inference.md에 이동·삭제·사용자 명확화 답변을 기록하고 체크리스트를 검토한다. (FR-053~056)

## 단계 38: 사용자 이야기 13 - 예제 전후처리

- [x] T083 [US13] tests/test_processing_boundary.py에 삭제·구현 소유권·코어 독립 가져오기 검증을 작성하고 기존 이미지 테스트의 경로를 이관한다. (SC-017)
- [x] T084 [US13] examples/step/yolo_pre_process.py·yolo_post_process.py에 네 이미지 모듈 구현을 옮기고 tensor_rt_pre_process.py·tensor_rt_post_process.py에서 재사용한다. (FR-053, FR-055)
- [x] T085 [US13] src/pipeworks/local_yolo_inference.py·embedded/__init__.py·cuda_async.py에서 감지 전용 실행·export·분류를 제거하고 embedded/yolo_detect.py 및 네 이미지 모듈을 삭제한다. (FR-053~054)
- [x] T086 [US13] tests의 프레임 해제·보고·설정·비동기·중앙 소스·Overlay 시나리오를 새 조합으로 이관하고 삭제 기능 전용 테스트를 정리한다. (FR-056)

## 단계 39: 현행 안내와 검증

- [x] T087 README.md·docs·examples에서 삭제 호출·레퍼런스를 정리하고 새 예제 소유권 및 조합을 안내한다. (FR-056)
- [x] T088 관련 실제 GPU·전후처리·보고·비동기·설정·Overlay 및 세 backend 중앙 배치 테스트를 실행하고 specs/027-yolo-inference/quickstart.md에 결과를 기록한다. (SC-017)

T082 → T083 → T084 → T085 → T086 → T087 → T088 순서로 진행한다. 서로 다른 전후처리 파일 작성은 독립적이나 이번 작업은 순차 수행한다. 코어 삭제와 모든 사용처 이관을 완료한 후 GPU 검증을 수행하고 수렴을 확인한다.

## 단계 40: 원격 예제 전달 수정

- [x] T089 specs/027-yolo-inference/spec.md·plan.md·research.md·contracts/yolo-inference.md에 오류 원인·수정 계약을 기록하고 명확화·체크리스트를 검토한다. (FR-057)
- [x] T090 [US14] tests/test_remote_example_dependencies.py에 실제 전달 payload의 새 프로세스 복원 회귀를 추가한다. (SC-018)
- [x] T091 [US14] src/pipeworks/main.py에서 재사용 메서드 정의 모듈을 함께 등록한다. (FR-057)
- [x] T092 테스트와 기존 원격 직렬화 회귀를 실행하고 specs/027-yolo-inference/quickstart.md에 기록한다. (SC-018)

T089 → T090 → T091 → T092 순서이며 수정은 직렬화 등록 범위에 한정한다.
