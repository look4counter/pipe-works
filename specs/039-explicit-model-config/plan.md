# 구현 계획: 모델 설정 경로 명시

## 요약과 기술 맥락
Python 3.11.9, PyTorch 및 TensorRT SDK이다. 선택적 config_path를 YoloInference에서 배치 작업자 및 설정 로더로 전달한다. 일반 백엔드의 외부 생성자 계약은 유지한다. 추가 의존성은 없다.

## 규칙 검토
AGENTS.md의 한글 문서와 speckit 절차를 적용한다. 헌법은 미작성 템플릿이다. 설계 전후 규칙 위반은 없다.

## 구조와 설계
- src/pipeworks/embedded/yolo_inference.py: 생성자 경로 및 실행 경로 전달.
- src/pipeworks/yolo_backend.py: 배치 설정을 명시 파일에서 로드.
- src/pipeworks/yolo_backends/tensorrt.py: 자동 파일 탐색 제거 및 명시 경로 수용.
- src/pipeworks/local_yolo_inference.py: 설정 경로를 작업자 생성과 캐시 구분에 사용.
- examples/01_single_stream_rtsp_style.py 및 docs/: 명시 경로 예제와 계약 갱신.
- tests/: 설정 적용·자동 탐색 제거·캐시 격리 및 회귀 검증.

## 검증
GPU가 필요 없는 파일 로딩·캐시 계약을 우선 검증하고 기존 관련 테스트를 실행한다. 실제 GPU 또는 RTSP 환경에 의존하는 검증은 결과에서 분리해 보고한다. 파일 경로가 다른 설정은 독립 작업자를 사용한다. 플러그인 상대 경로 기준은 모델 디렉터리로 유지한다.
