# 작업 목록: 예제 전후처리 통일

## 1단계: 준비

- [X] T001 examples/, tests/, tools/, src/, README.md와 docs/의 전용 클래스 사용처를 검토한다. (FR-001~FR-004)

## 2단계: 사용자 이야기 1

- [X] T002 [US1] examples/01_single_stream_rtsp_style.py를 YOLO로 전환하고 examples/step/의 두 전용 파일을 삭제한다. (FR-001, FR-002)
- [X] T003 [US1] tests/의 전후처리·보고·원격 전달 검증을 통합 구현에 맞춘다. (FR-003, SC-001, SC-002)
- [X] T004 [US1] tools/의 현재 구현과 src/pipeworks/embedded/cuda_async.py의 삭제 클래스 분기를 정리한다. (FR-004, SC-003)
- [X] T005 [US1] README.md와 docs/의 사용법을 갱신한다. (FR-002)

## 3단계: 검증

- [X] T006 관련 tests/와 tools/를 실행하고 참조 검색 및 구현 대조를 수행한다. (SC-001~SC-003)

## 의존성과 전략

T001 → T002 → T003 → T004 → T005 → T006 순서다. 파일별 독립 수정은 병렬 가능하지만 이번에는 순차 작업한다. 최소 완성 범위는 사용자 이야기 1 전체다.


## 4단계: 사용자 이야기 2

- [X] T007 [US2] examples/step/metadata_from_db.py와 save_inference_result_to_db.py 및 tests/test_metadata_from_db.py를 삭제한다. (FR-005, FR-006)
- [X] T008 [US2] src/, examples/, tests/, docs/, tools/와 README.md의 참조 부재 및 예제 구문·가져오기를 검증한다. (SC-004)

T007은 갱신한 명세·계획·작업 목록의 일관성 확인 후 수행하며 T008은 T007에 의존한다. 삭제 외 구현 변경은 없다.

