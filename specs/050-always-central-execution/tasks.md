# 작업 목록: 배치 여부와 독립적인 중앙 실행

## 1단계: 준비

- [x] T001 specs/050-always-central-execution/spec.md와 설계 산출물의 요구사항 및 .gitignore를 확인한다.

## 2단계: 기반 검증

- [x] T002 tests/test_pipeline_routing.py의 실행 계약 검증을 항상 중앙 실행으로 변경한다.
- [x] T003 tests/test_central_process.py의 batch_server 표기와 실제 Pipeline 사용을 갱신하고 문법을 검증한다.

## 3단계: 사용자 이야기 1

- [x] T004 [US1] src/pipeworks/pipeline.py의 배치 감지 함수와 로컬 실행 분기를 제거한다. FR-001, FR-002, FR-004.
- [x] T005 [US1] tests/test_inference_contract.py의 개별 추론 검증으로 공유 배치 미호출을 확인한다. FR-003.
- [x] T006 [US1] README.md와 docs/pipeworks/pipeline.md, main.md, getting_started.md, embedded/yolo_inference.md를 갱신한다. FR-005.

## 4단계: 검증과 마무리

- [x] T007 specs/050-always-central-execution/quickstart.md에 경로·추론 회귀 및 실제 중앙 실행 결과와 환경 제약을 기록한다.

## 의존성과 실행 전략

T001 → T002·T003 → T004 → T005·T006 → T007 순서로 실행한다. 단일 사용자 이야기 전체가 최소 제공 범위다. 검증 파일과 문서는 서로 다른 파일이므로 병렬 작업이 가능하지만 이번 작업은 순차 수행한다. 독립 인수 기준은 배치 참·거짓 모두 중앙 실행하며 거짓은 공유 배치를 호출하지 않는 것이다.

## 5단계: 수렴

- [x] T008 FR-005와 SC-003의 부분 충족을 해소한다. README.md 및 docs/pipeworks/main.md의 배치 전용 소개와 docs/pipeworks/pipeline.md의 로컬 오류 안내를 항상 중앙 실행 계약에 맞춘다.
