# PipeWorks 사용 설명서

배포본의 specs 없이 이 문서만으로 별도 애플리케이션을 구성할 수 있도록 사용 절차와 src의 모듈 계약을 연결합니다. examples는 참고용이며 원하는 앱 디렉터리에서 pipeworks를 가져와 사용할 수 있습니다.

## 사용 순서

1. [환경 설치와 별도 앱 실행](getting_started.md)
2. [설정 파일·경로·실시간 변경](configuration.md)
3. [Pipeline 조립과 실행](pipeline.md), [Step·PipelineContext](models.md)
4. [사용자 Step 작성](custom_steps.md), [사용자 GPU 실행부](yolo_backend.md)
5. [문제 해결](troubleshooting.md)

## 가져오기와 사용 범위

src/pipeworks/__init__.py는 Pipeline과 Backend를 제공합니다. src/pipeworks/embedded/__init__.py는 아래 내장 Step 10개와 Backend를 제공합니다. Step·PipelineContext는 pipeworks.models에서, Hotswap은 pipeworks.hotswap에서 가져옵니다. src/pipeworks/yolo_backends/__init__.py는 추가 편의 API가 없는 실행부 패키지입니다.

일반 앱의 조립 API는 Pipeline·Step·PipelineContext·Backend·내장 Step입니다. 사용자 GPU 처리에는 execution의 수명 신호와 yolo_backend의 실행부 계약을 참고합니다. 나머지 작업자·수집기·감시 모듈은 내부 구조를 설명하는 참고 API이며 앱이 직접 조립할 필요가 없습니다. 밑줄 이름은 내부 구현입니다.

## Step 명세

examples를 제외한 src의 구체 Step 11개가 아래에 대응됩니다. 문서명은 해당 Step의 구현 모듈명을 따릅니다.

| Step | 구현 모듈 | 명세 |
| --- | --- | --- |
| RTSPSource | src/pipeworks/embedded/rtsp_source.py | [RTSPSource](embedded/rtsp_source.md) |
| NvidiaDecode | src/pipeworks/embedded/nvidia_decode.py | [NvidiaDecode](embedded/nvidia_decode.md) |
| YoloInference | src/pipeworks/embedded/yolo_inference.py | [YoloInference](embedded/yolo_inference.md) |
| NvidiaEncode | src/pipeworks/embedded/nvidia_encode.py | [NvidiaEncode](embedded/nvidia_encode.md) |
| RTSPPublish | src/pipeworks/embedded/rtsp_publish.py | [RTSPPublish](embedded/rtsp_publish.md) |
| EveryNFrames | src/pipeworks/embedded/every_n_frames.py | [EveryNFrames](embedded/every_n_frames.md) |
| CudaAsync | src/pipeworks/embedded/cuda_async.py | [CudaAsync](embedded/cuda_async.md) |
| TapSkipIfBusy | src/pipeworks/embedded/tap_skip_if_busy.py | [TapSkipIfBusy](embedded/tap_skip_if_busy.md) |
| StreamReport | src/pipeworks/embedded/stream_report.py | [StreamReport](embedded/stream_report.md) |
| YoloReport | src/pipeworks/embedded/yolo_report.py | [YoloReport](embedded/yolo_report.md) |
| Hotswap | src/pipeworks/hotswap.py | [Hotswap](hotswap.md) |

내장 Step 10개는 `pipeworks.embedded`에서, Hotswap은 `pipeworks.hotswap`에서 가져옵니다.

## 공통 계약

[Step와 PipelineContext](models.md)의 configure와 process는 필수 추상 메서드입니다. PipelineContext는 동적 속성 컨테이너이고 모든 단계가 같은 필드를 제공하지는 않습니다. 각 단계의 입력·출력 계약에 맞춰 연결합니다. RTSPPublish는 출력 없는 Sink이며 NvidiaDecode와 NvidiaEncode는 새 컨텍스트를 생성합니다. 보고 단계는 입력 객체를 그대로 전달합니다.

설정 가능한 내장 Step은 YAML 값, 최초 생성자 값, 기본값 순서로 적용합니다. YAML에서 옵션을 삭제하면 최초 생성자 값으로 돌아갑니다. CudaAsync·EveryNFrames의 내부 Step은 각 클래스명 YAML 섹션을 사용하고 TapSkipIfBusy는 자기 섹션을 감싼 Step에 위임합니다. 전체 실행과 설정 감시는 [Pipeline](pipeline.md)을 참고하세요.

## 보충 문서

[TensorRT 실행부](embedded/tensor_rt_inference.md)는 YoloInference의 backend 상세 문서이며 별도의 TensorRTInference Step을 제공한다는 뜻이 아닙니다. YOLO 전후처리와 Overlay 등 examples의 Step은 이 목록의 대상이 아닙니다.

기존 async.md와 detection_report.md는 구현 모듈명에 맞춰 각각 cuda_async.md와 yolo_report.md로 변경했습니다.

## Step 외 모듈 명세

| 구현 | 문서 | 사용 범위 |
| --- | --- | --- |
| src/pipeworks/pipeline.py | [Pipeline](pipeline.md) | 앱 조립·실행 |
| src/pipeworks/models.py | [Step·PipelineContext](models.md) | 앱 확장·데이터 계약 |
| src/pipeworks/backend.py | [Backend](backend.md) | 실행부 선택 |
| src/pipeworks/execution.py | [실행 수명 신호](execution.md) | 사용자 GPU 단계·취소 협력 |
| src/pipeworks/yolo_backend.py | [GPU 실행부 계약](yolo_backend.md) | 사용자 backend 확장 |
| src/pipeworks/inference_contract.py | [전후처리 연결](inference_contract.md) | 전후처리 프로파일·임시 필드 |
| src/pipeworks/main.py | [중앙 프로세스](main.md) | 내부 실행·배포 조건 |
| src/pipeworks/local_yolo_inference.py | [공유 GPU 추론](local_yolo_inference.md) | 직접 infer·내부 작업자 |
| src/pipeworks/batch_collector.py | [배치 수집기](batch_collector.md) | 내부 참고 |
| src/pipeworks/model_worker.py | [모델 경로 캐시](model_worker.md) | 내부 참고 |
| src/pipeworks/file_watch.py | [공유 파일 감시](file_watch.md) | 내부 참고 |
| src/pipeworks/yolo_backends/torchscript.py | [TorchScript](yolo_backends/torchscript.md) | 내장 실행 구현 |
| src/pipeworks/yolo_backends/ultralytics.py | [Ultralytics](yolo_backends/ultralytics.md) | 내장 실행 구현 |
| src/pipeworks/yolo_backends/tensorrt.py | [TensorRT](yolo_backends/tensorrt.md) | 내장 실행 구현 |

패키지 초기화 모듈 세 개의 공개 범위는 위의 가져오기 설명과 [실행부 패키지](yolo_backends/README.md)에 기록되어 있습니다. Hotswap은 Step 표에 포함합니다. 이 목록은 examples와 배포 생성물·캐시를 제외한 src의 모든 Python 모듈을 다룹니다.
