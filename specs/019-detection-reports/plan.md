# 구현 계획: 감지 성능 리포트

**날짜**: 2026-10-09 | **명세**: [spec.md](spec.md)

## 요약

실행별 통계와 요청별 프로파일을 만들고 두 공개 Report Step으로 출력한다. CPU 경과 시간은 perf_counter, GPU 구간은 CUDA Event로 기록한다. 미완료 이벤트는 query로 확인하며 추가 synchronize는 호출하지 않는다.

## 기술 배경

Python 3.11, PyTorch 2.2.1, Ultralytics 8.4.146, TensorRT 10.10을 사용한다. 기존 unittest 및 CUDA 테스트를 실행한다. 영구 저장소나 새 의존성은 없다.

## 원칙 점검

헌법은 미작성 템플릿이므로 규범 점검을 생략한다. AGENTS.md의 한글 문서와 speckit 순서를 준수한다. 기존 사용자 수정 예제를 보존하면서 Report만 추가한다. 설계 후에도 위반 사항이 없다.

## 구조와 설계

- `src/pipeworks/detection_profile.py`: 요청 프로파일, CPU/GPU 구간, 실행별 통계, 활성 상태, 최근 10초 및 최대 10000개 표본 제한.
- `src/pipeworks/embedded/yolo_detect_report.py`, `tensor_rt_report.py`: 공통 출력 구현을 상속하는 공개 Step.
- `src/pipeworks/embedded/stream_report.py`: 기존 실행 통계에 감지 저장소 연결.
- `src/pipeworks/embedded/yolo_detect.py`, `local_yolo.py`: 전처리, predictor inference와 postprocess, 좌표 복원, 상태 기록.
- `src/pipeworks/embedded/tensor_rt_inference.py`, `local_tensor_rt.py`, `examples/step/tensor_rt_pre_process.py`, `tensor_rt_post_process.py`: 모델 준비, 입력 대기·결합·출력 복사와 감지 계측.
- `src/pipeworks/embedded/cuda_async.py`: 타임아웃·작업자 바쁨과 부분 종료 기록.
- `src/pipeworks/embedded/__init__.py`, `examples/01_single_stream_rtsp_style.py`, `README.md`, `docs/pipeworks/embedded/detection_report.md`: 공개 API와 사용 안내.
- `tests/test_detection_report.py`: 통계 격리, 이벤트, 종료, 배치 전달 및 상태 검증.

프로파일은 구간을 누적하고 요청 종료 시 원래 실행 저장소로 전달한다. 공유 배치 작업자는 독립 프로파일을 채우고 선택적 콜백으로 호출자에 전달한다. 같은 구간의 여러 부분은 요청별로 합산한다. GPU 시간은 CPU 시간과 합산하지 않는다. 리포트는 상류 처리 전 활성화한다. 최근 10초와 최대 10000개 표본으로 메모리를 제한한다.

## 검증

모의 이벤트로 평균·10초 만료·미완료 보류를 검증한다. 입력 정체·종료·범위 격리를 확인한다. CUDA 단일·배치 계측과 기존 결과 보존 테스트를 실행한다. 마지막으로 speckit-converge를 수행한다.

## 후속 개선: 컴파일된 NMS 선택

`examples/step/tensor_rt_post_process.py`에서 모듈 초기화 시 torchvision을 명시적으로 가져온다. 설치된 Ultralytics는 sys.modules에 torchvision이 있으면 torchvision.ops.nms를 선택한다. 기존 torchvision 의존성을 사용하므로 추가 패키지는 필요하지 않다. 기존 NMS 호출과 후처리 알고리즘은 유지한다.

새 프로세스에서 후처리 모듈을 가져온 후 torchvision 로드를 확인하고 CUDA 후보를 입력하여 torchvision.ops.nms 호출을 관찰한다. 기존 `tests/test_tensor_rt_processing.py`와 `tests/test_detection_report.py`를 실행하여 감지 결과와 계측을 검증한다. 헌법은 미작성 템플릿이고 설계 원칙 위반은 없다.
