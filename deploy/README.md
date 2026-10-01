# 배포 템플릿

이 디렉터리는 기본 SDK와 Observability Endpoint를 컨테이너로 실행하는
최소 배포 예제다.

## 실행

저장소 루트에서 실행한다.

    docker compose -f deploy/docker-compose.yml up --build

실행 후 다음 주소를 사용할 수 있다.

- `http://localhost:8080/health`
- `http://localhost:8080/metrics`

기본 이미지는 외부 RTSP, GPU, MQ 없이 Synthetic Source를 사용한다. 실제
배포에서는 `examples/06_observability_server.py`의 `build_pipeline()`을
프로젝트 Pipeline으로 교체하고, Dockerfile의 optional extra를 선택한다.

## 운영 교체 지점

- GStreamer RTSP: `pip install .[gstreamer]`와 시스템 GStreamer 런타임
- YOLO: `pip install .[yolo]`와 모델 파일 마운트
- MQ: `pip install .[mq]`와 Broker 주소/Secret 주입
- GPU/TensorRT: CUDA 및 TensorRT가 포함된 베이스 이미지 사용

운영 환경의 Secret, 모델, RTSP 주소는 이미지에 굽지 말고 환경 변수나
배포 Secret으로 주입한다. `/health`는 readiness 확인에, `/metrics`는
Prometheus scrape 대상에 사용한다.
