# 구현 계획: 모델 동명 설정 복원

## 요약과 기술 맥락
Python 3.11.9 GPU SDK이다. 모델 경로에서 동명 YAML을 유도하고 별도 설정 경로를 제거한다. 추가 의존성은 없다.

## 규칙 검토
한글 문서와 speckit 절차를 적용한다. 헌법은 미작성 템플릿이다. 설계 전후 위반은 없다.

## 구조와 설계
src/pipeworks/embedded/yolo_inference.py, local_yolo_inference.py 및 yolo_backends/tensorrt.py에서 config_path 전달을 제거한다. yolo_backend.batch_settings와 TensorRT 설정 로더는 model_path.with_suffix('.yml')을 읽고 미존재 기본값을 유지한다. 작업자 캐시는 backend 아래 정규 모델 경로로 단순화한다.
examples/01_single_stream_rtsp_style.py, tests/ 및 README.md와 docs/의 설정 선택·캐시 설명을 갱신한다.

## 검증
동명 탐색·기본값·YAML 오류·제거 인자·캐시 재사용을 먼저 검사한다. 관련 실제 GPU, TensorRT와 중앙 배치 테스트를 실행하고 config_path가 모델 API에 남지 않았는지 검색한다. Pipeline.config_path는 별개이므로 유지한다.
