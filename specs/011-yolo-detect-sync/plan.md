# 구현 계획: 동기 GPU YOLO 감지

**작성일**: 2026-10-09 · **명세**: [spec.md](spec.md)

## 기술 환경과 규칙

Python 3.11.9, 기존 PyTorch CUDA와 Ultralytics를 사용한다. 추가 의존성은 없다. 헌장은 미작성 템플릿이므로 원칙 검증을 생략한다. 모든 문서는 한글로 작성하고 speckit 순서를 준수한다. 사용자 변경과 이전 Async 구현을 보존한다.

## 설계

yolo_detect.py에서 요청 자료형, 데몬 작업자, 시간 제한 설정과 대기를 제거한다. 모델은 process 입력 스트림의 첫 선택 프레임에서 지연 로드하고 재사용한다. 입력 CUDA 스트림에서 준비 이벤트를 기록하고 별도 추론 CUDA 스트림이 이를 기다린 뒤 GPU NV12 변환·추론·좌표 복원·결과 완료를 수행한다. Python 실행은 호출 스레드에서 동기 진행하지만 원본 영상 CUDA 스트림에 추론 작업을 제출하지 않는다. 동기 처리 중에는 원본을 보관하므로 별도 GPU 입력 복제가 필요하지 않다.

예측 헬퍼는 요청 객체 대신 텐서·옵션·스트림을 직접 받는다. 추론 시작부터 GPU 완료까지 시간을 호출자의 StreamReport 문맥에 기록한다. 변환·로드 오류는 추론 통계에서 제외하며 모델 예측 오류는 예외를 전파하면서 실제 추론 시간을 기록한다. 예외 시 이미 제출한 CUDA 작업은 해당 스트림에서 정리하고 원래 오류를 전파한다.

TensorRTInference는 기존 _AsyncWorker를 상속하므로 필요한 슬롯 초기화·예약·제출·종료 메서드를 자체 _InferenceWorker로 옮긴다. TensorRT의 추론 코드·시간 제한·결과·통계 계약은 변경하지 않는다.

공통 Async로 감싸는 경우 기존 입력 복사·시간 제한·오류 원본 통과 정책을 적용한다. 모델 동명 YAML은 단일 YoloDetect에서 더 이상 읽지 않는다. 구성·간격·GPU 결과 계약은 유지한다.

## 파일과 검증

- src/pipeworks/embedded/yolo_detect.py: 동기 처리와 GPU 수명.
- src/pipeworks/embedded/tensor_rt_inference.py: 작업자 의존성 분리.
- tests/test_yolo_detect.py: 호출 스레드, 초기화·추론 대기, 간격·오류 전파·GPU 결과·통계·Async 조합 검증.
- tests/test_tensor_rt_inference.py, tests/test_async.py, tests/test_local_yolo.py, tests/test_yolo_detect_batch.py: 기존 경로 회귀 검증.
- README.md와 docs/pipeworks/embedded/yolo_detect.md, docs/pipeworks/embedded/async.md: 현재 동작 안내.
- specs/011-yolo-detect-sync/: 현재 명세와 계약, 검증 기록.

집중 테스트를 먼저 작성하여 구현 전 실패를 확인한다. 이벤트로 대기를 제어하고 실제 모델을 CPU 복사 금지 상태에서 실행한다. 이후 관련 회귀와 전체 검증을 수행하고 수렴 점검한다. GPU 변경과 프레임 간격, 빈 결과도 확인한다.

## 헌장 재확인

설계 후 충돌이나 미해결 질문은 없다. TensorRT 작업자 분리는 기존 사용자를 깨뜨리지 않기 위한 최소 통합 변경이다.
