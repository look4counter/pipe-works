# 구현 계획: 예제 전후처리 통일

## 기술 맥락과 요약
Python 3.11.9 GPU SDK이다. 기존 두 래퍼는 YOLO 메서드를 재사용하므로 사용처를 직접 YOLO 구현에 연결한다. 추가 의존성은 없다.

## 규칙 검토
한글 문서와 speckit 절차를 적용한다. 헌법은 미작성 템플릿이다. 설계 전후 위반은 없다.

## 구조와 설계
examples/step/의 두 TensorRT 전용 파일을 삭제하고 examples/01_single_stream_rtsp_style.py의 가져오기와 생성자를 교체한다. tests/는 기존 실행 시나리오를 YOLO로 전환하며 중복 클래스 조합은 줄인다. tools/의 현재 구현은 YOLO로 바꾸되 과거 Git 경로와 클래스 이름은 기준 구현 호환용으로 허용한다. src/pipeworks/embedded/cuda_async.py의 삭제 클래스 보고 분기를 정리하고 실제 backend 보고는 유지한다. README.md와 docs/의 안내를 통일한다.

## 검증
전후처리·원본 수명·GPU 탐지·보고·원격 직렬화 테스트를 실행한다. 모듈 가져오기 및 문법을 검증하고 벤치마크는 작은 반복 수로 실행하여 기준 구현과 비교한다.

## 추가 정리 계획

examples/step/metadata_from_db.py와 save_inference_result_to_db.py를 삭제하고 전용 tests/test_metadata_from_db.py를 제거한다. 실행 파이프라인과 사용자 문서에는 사용처가 없다. 남은 예제 구문 검사·참조 검색·원격 예제 가져오기 검증으로 확인한다. 새 테스트는 작성하지 않는다.
