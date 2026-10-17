# 구현 계획: 모델 배치 설정 단순화

## 요약과 기술 맥락
Python 3.11.9의 GPU 영상 SDK이다. 모델 설정 로더의 배치 키를 교체하고 TensorRT 외부 플러그인 지원을 제거한다. 추가 의존성은 없다.

## 규칙 검토
한글 문서와 speckit 절차를 적용한다. 헌법은 미작성 템플릿으로 구체 원칙 적용을 생략한다. 설계 전후 위반은 없다.

## 구조와 설계
src/pipeworks/yolo_backend.py와 local_yolo_inference.py의 배치 키 및 검증 메시지를 변경한다. yolo_backends/tensorrt.py의 _engine_settings와 외부 로드·핸들 관리를 제거하고 _EngineSession은 모델 경로와 profile_index만 받게 한다. embedded/yolo_inference.py의 전달 코드를 정리한다. 표준 플러그인 초기화는 유지한다.
examples/model/, tests/ 및 README.md와 docs/의 해당 계약을 갱신한다.

## 검증
새 키와 이전 키 검증을 먼저 테스트한다. 파일 로딩, 실제 GPU 배치, TensorRT 엔진과 중앙 실행 회귀 테스트를 수행한다. 모델 설정 외 timeout_ms는 변경하지 않았는지 검색한다.

## 명칭 변경 계획

수집 로직은 유지하고 모델 설정 키·검증 메시지·예제·문서를 max_batch_wait_ms로 통일한다. 이전 batch_timeout_ms를 오류 처리하는 회귀 검증을 추가한다. 값과 단위, 기본값 및 다른 timeout_ms는 유지한다.
