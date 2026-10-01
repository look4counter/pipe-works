# 운영 패키징

Pipe Works의 기본 설치는 외부 영상 장치, GPU, Broker 없이 SDK 핵심 DSL과
결정적 테스트를 실행할 수 있는 최소 구성이다. 운영 기능은 필요한 extra만
선택해서 설치한다.

지원 Python 범위는 `>=3.11,<3.15`다. 특정 패치 버전에 고정하지 않아 운영
이미지의 보안 패치와 최신 패치 릴리스를 함께 사용할 수 있다.

## 기본 설치

프로젝트 루트에서 다음 명령을 사용한다.

    python -m pip install .

기본 설치에는 Python SDK, DSL, Worker Runtime, 로컬 Source, 메모리 기반
Output과 테스트 가능한 Action이 포함된다.

## 운영 extra

    python -m pip install ".[gstreamer]"
    python -m pip install ".[yolo]"
    python -m pip install ".[mq]"
    python -m pip install ".[all]"

- `gstreamer`: PyGObject와 GStreamer 기반 RTSP 수신 경계
- `yolo`: Ultralytics YOLO 추론 경계
- `mq`: RabbitMQ용 pika Action 경계
- `all`: 위 세 가지를 한 번에 설치

GStreamer와 CUDA/TensorRT 런타임은 운영체제와 GPU 드라이버에 따라 별도로
설치해야 한다. Python extra 설치만으로 시스템 런타임이 준비되지는 않는다.

## 설치 확인

    pipeworks --version
    pipeworks --check

설치하지 않은 optional runtime을 사용하는 Pipeline은 실행 시 어떤 패키지와
런타임이 필요한지 설명하는 오류를 반환한다. 기본 SDK import는 optional
패키지가 없어도 성공해야 한다.

## 배포 원칙

- 애플리케이션은 Python DSL에 Source, Model, Action, Output의 정체성을 적는다.
- timeout, retry, device, codec, queue와 같은 운영 조정값은 YAML에 둔다.
- GPU와 Media runtime은 별도 이미지 또는 호스트 계층에서 관리한다.
- 운영 이미지에는 필요한 extra만 설치해 공격 면적과 시작 시간을 줄인다.
- 배포 전 `pytest`, `ruff`, `pipeworks --check`를 실행한다.

TensorRT Adapter는 CUDA buffer binding 방식이 배포 환경마다 다르므로
프로젝트의 로더를 `TensorRTSessionFactory(loader=...)`로 주입한다. 팩토리는
엔진 경로별 Session을 지연 생성하고 재사용한다. Session은 `infer`,
`infer_batch`, `reset` 계약을 구현하고, 일시적인 CUDA 오류 뒤에는 SDK가
`inference_retry` 설정에 따라 `reset()` 후 재시도한다. 배포 재시작이나 엔진
교체 시에는 `factory.clear(path)` 또는 `factory.clear()`로 CUDA 자원을 정리한다.

현재 저장소의 RTSP-출력 통합 테스트는 실제 장비 없이도 실행할 수 있도록
GStreamer `frame_reader`와 MediaMTX `publisher`를 주입한다. 이 테스트는
프레임 디코딩 payload 자체가 아니라 stream ID, sequence, 배치 결과, 출력 URL
라우팅을 검증한다. 실제 운영 검증에서는 동일한 DSL에 배포 어댑터를 연결하고
카메라, GPU, MediaMTX가 포함된 별도 환경 테스트를 추가한다.
