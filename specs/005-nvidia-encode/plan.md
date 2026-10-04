# 구현 계획: NVIDIA 비디오 인코딩

**명세**: [기능 명세](spec.md)

## 기술 배경

- [NVIDIA 디코딩 단계](../006-nvidia-decode/plan.md)는 프레임, 비디오 스트림, CUDA 스트림, 픽셀 형식을 담은 `PipelineContext`를 전달한다.
- `RTSPPublish`는 `packet`과 `video_stream`을 가진 컨텍스트를 받으며 패킷의 PTS·DTS·시간 기준을 사용한다.
- NVIDIA 인코더의 `Encode()`와 `EndEncode()` 결과는 여러 압축 항목을 포함할 수 있다.

## 설계

1. `configure()`에서 GPU 번호와 FPS를 읽고 FPS가 양수인지 확인한다.
2. 첫 프레임에서 입력 스트림의 코덱·크기와 픽셀 형식으로 NVIDIA 인코더를 만든다. 인코더의 FPS, GOP, IDR 간격은 설정된 FPS를 사용한다.
3. `encoded_bytes()`에서 바이트열, 사전, 중첩 목록의 압축 데이터를 추출한다. 알 수 없는 형식은 오류로 드러낸다.
4. `process()`의 `output_packet()`에서 인코더 결과를 항목별로 순회한다. 비어 있지 않은 항목마다 `av.Packet`을 만들고 순차 PTS·DTS, FPS의 역수인 시간 기준, 지속 시간을 넣는다.
5. 정상 입력 종료 시 `EndEncode()`로 잔여 결과를 회수하고 동일한 변환을 적용한다.

## 단계 계약

- **입력**: [입력 자료 모델](data-model.md)에 기술한 프레임 컨텍스트.
- **출력**: `packet`과 `video_stream`이 있는 `PipelineContext`. [RTSP 송출 명세](../004-rtsp-publish/spec.md)의 입력 계약을 충족한다.

## 영향 파일

- `src/pipeworks/embedded/nvidia_encode.py`

## 검증

- 모의 인코더로 다중 결과, 사전·중첩 데이터, 빈 결과, 종료 잔여 결과, 시간 정보를 확인한다.
- 소스 구문 검사와 RTSP 송출 단계 테스트를 실행한다.
- 실제 GPU 인코딩과 RTSP 송출은 해당 장비와 서버가 있는 환경에서 별도로 확인한다.
