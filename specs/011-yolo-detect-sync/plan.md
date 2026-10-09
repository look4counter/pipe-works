# 구현 계획: 동기 GPU YOLO 감지

**작성일**: 2026-10-09 · **명세**: [spec.md](spec.md)

## 기술 환경과 규칙

Python 3.11.9, 기존 PyTorch CUDA와 Ultralytics를 사용한다. 추가 의존성은 없다. 헌장은 미작성 템플릿이므로 원칙 검증을 생략한다. 모든 문서는 한글로 작성하고 speckit 순서를 준수한다. 사용자 변경과 이전 Async 구현을 보존한다.

## 설계

## 별도 배치 Step 제거

yolo_detect_batch.py와 embedded 공개 내보내기를 제거한다. examples/02_multiple_stream_rtsp_style.py는 YoloDetect(..., batch=True)로 옮기고 단일 영상 예제의 사용자 변경은 보존한다. 기존 tests/test_yolo_detect_batch.py는 tests/test_yolo_batch.py로 옮겨 새 API를 검증한다. 폐기된 클래스 전용 low_latency 설정 검증은 제거하고 GPU 입력과 gpu_id가 일치하도록 검증 데이터를 정정한다. BoxOverlay 예제 검사는 Async 내부 YoloDetect 위치를 확인한다. README의 별도 Step 항목과 배치 문서를 제거하고 YOLO·Async·local_yolo 안내 및 문서 링크를 통합한다. 과거 명세·작업 이력은 남기되 최신 계약은 제거 결정으로 대체한다. 집중 검증과 전체 회귀 검증 후 수렴을 확인한다.

## 선택적 배치와 입력 사용 종료 신호

`YoloDetect(model_path, *, batch=False)`에서 불리언을 검증한다. True일 때 자체 배치 처리 반복자에서 현재 설정으로 GPU NV12 입력을 검증·복제하고 완료 이벤트를 만든 뒤 release_input과 local_yolo.infer를 직접 호출한다. YoloDetectBatch 인스턴스나 처리 반복자를 생성하지 않는다. 입력마다 현재 설정을 조회하여 실행 중 설정 갱신을 유지한다. False는 기존 경로를 그대로 사용한다. 배치 오류 통과 정책은 기존 배치와 동일하며 단일 모드의 오류 전파는 유지한다.

`src/pipeworks/execution.py`에 ContextVar 기반 선택적 `release_input(*, ready_event=None)`와 내부 요청 범위를 추가한다. Async 작업자가 각 next 호출에 해당 요청의 콜백을 설정하고 종료 시 복원한다. 준비 이벤트를 가진 신호는 슬롯 잠금 아래 해당 요청에 보관한다. 타임아웃 시 잠금 아래 이벤트 query로 완료를 확인하고, 완료 신호가 있을 때만 snapshot을 생략한다. 조회 실패는 로그와 기존 복사로 처리한다. 다른 요청·다른 파이프라인·중첩 Async에 신호가 새지 않아야 한다.

YoloDetect의 자체 배치 경로는 원본 메타데이터를 먼저 읽고 GPU 입력 복사 이벤트를 만든 뒤 신호를 전달한다. 별도 배치 클래스는 제거하고 이 계약을 통합 API로 제공한다. 배치 대기 중에는 복사본만 사용한다. GPU 완료 전 불필요한 호스트 대기를 추가하지 않는다. Async 입력은 읽기 전용이며 요청의 원본 수명은 기존 방식으로 보관한다. 단일 모드는 신호를 보내지 않고 기존 타임아웃 복사를 유지한다. TensorRT와 모델 공유 키는 변경하지 않는다.

검증 파일은 tests/test_yolo_detect.py, tests/test_yolo_batch.py, tests/test_async.py, tests/test_local_yolo.py이다. 기본 경로·직접 배치 처리·모드 검증·설정 갱신과 실제 GPU 복사 완료 후 무복사 통과, 이벤트 미완료·조회 오류·요청 격리·신호 없는 기존 경로를 검증한다. README와 YOLO·Async 문서 및 관련 명세 계약을 갱신한다. BoxOverlay 예제 검사는 Async 내부 감지 Step을 확인하도록 수정한다.

yolo_detect.py에서 요청 자료형, 데몬 작업자, 시간 제한 설정과 대기를 제거한다. 모델은 process 입력 스트림의 첫 선택 프레임에서 지연 로드하고 재사용한다. 입력 CUDA 스트림에서 준비 이벤트를 기록하고 별도 추론 CUDA 스트림이 이를 기다린 뒤 GPU NV12 변환·추론·좌표 복원·결과 완료를 수행한다. Python 실행은 호출 스레드에서 동기 진행하지만 원본 영상 CUDA 스트림에 추론 작업을 제출하지 않는다. 동기 처리 중에는 원본을 보관하므로 별도 GPU 입력 복제가 필요하지 않다.

예측 헬퍼는 요청 객체 대신 텐서·옵션·스트림을 직접 받는다. 추론 시작부터 GPU 완료까지 시간을 호출자의 StreamReport 문맥에 기록한다. 변환·로드 오류는 추론 통계에서 제외하며 모델 예측 오류는 예외를 전파하면서 실제 추론 시간을 기록한다. 예외 시 이미 제출한 CUDA 작업은 해당 스트림에서 정리하고 원래 오류를 전파한다.

TensorRTInference는 기존 _AsyncWorker를 상속하므로 필요한 슬롯 초기화·예약·제출·종료 메서드를 자체 _InferenceWorker로 옮긴다. TensorRT의 추론 코드·시간 제한·결과·통계 계약은 변경하지 않는다.

공통 Async로 감싸는 경우 정상 경로는 무복사이며 타임아웃에 후속 전달용 복사를 수행한다. 배치 입력 사용 종료 이벤트가 완료되었으면 이 복사도 생략한다. 모델 동명 YAML은 단일 YoloDetect에서 읽지 않고 배치 모드에서만 수집 설정으로 사용한다. 구성·간격·GPU 결과 계약은 유지한다.

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
