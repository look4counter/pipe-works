# 작업 목록: 미디어 파이프라인

`[x]`는 현재 소스 구현을 확인한 항목이다. `[ ]`는 미구현 또는 자동화 검증이 부족한 항목이다.

## 설정과 수신

- [x] T001 Implement the `PipelineArguments` model, `nvidia`/`bypass` CLI validation, and GPU/FPS defaults.
- [x] T002 RTSP URL 접두사·boolean·양의 정수·활성 단계 경로 검증을 구현한다.
- [x] T003 첫 비디오 스트림 패킷 수신, 5초 timeout, 컨테이너 정리와 3초 재연결을 구현한다.
- [x] T004 `tests/unit/test_receive.py`에 비디오 스트림 선택·빈 패킷·FFmpeg 오류·재연결 사례를 추가한다.

## NVIDIA 프레임 경로

- [x] T005 `ReceivePacket`, `FrameContext`, `EncodedPacket` 데이터 모델을 구현한다.
- [x] T006 `nvidia_pipe/decode.py`에 PyNvVideoCodec 디코더 연결을 구현한다.
- [x] T007 `nvidia_pipe/encode.py`에 PyNvVideoCodec 인코더 연결과 패킷 바이트 변환을 구현한다.
- [x] T008 `send.py`에 RTSP 출력 mux 경로를 구현한다.
- [x] T009 `cli.py`에 수신·디코드·사용자 단계·인코드·송신 흐름을 연결한다.
- [x] T010 GPU 없는 단위 테스트에서 encoder/decoder API 인자와 encoder 초기화 오류 전파를 검증한다.
- [x] T011 NVIDIA/RTSP 입력부터 출력까지 통합 테스트를 추가하고 DB 설정으로 실행한다. (`tests/integration/test_nvidia_rtsp_pipeline.py`; 현재 환경에서 통과)
- [x] T012 인코더 출력 codec 설정과 생성 timestamp를 사용한 출력 mux 구성·변경 테스트를 추가한다.
- [x] T013 RTSP 입력 stream 또는 codec·해상도 설정이 바뀌면 decoder/encoder를 재설정하고 이전 encoder 출력을 flush한다.

## 사용자 모듈

- [x] T014 Implement module loading for metadata `metadata()`, inference `on_frame(infer, parameters, frame)`, and postprocess `on_frame(parameters, frame)`.
- [x] T015 활성 모듈의 파일 변경을 1초 간격으로 감시하고 새 객체로 교체한다.
- [x] T016 pytorch inference 및 postprocess 콜백 결과를 다음 단계에 전달한다.
- [x] T017 metadata 활성화 시 최신 metadata 반환값을 각 `FrameContext.metadata`에 넣어 inference/postprocess로 전달한다.
- [x] T018 FRAME TYPE을 pytorch만 허용하고 ONNX CLI 선택지를 비활성화한다.
- [x] T019 Call the inference callback for every frame and pass `inference_interval` eligibility through `infer`.
- [x] T020 사용자 모듈 실제 reload, reload 실패 후 이전 모듈 유지·재시도, inference/postprocess 콜백 오류 시 원본 프레임 전달 테스트를 작성한다.

## 종료와 상태

- [x] T021 stop event로 receive loop를 중단하고 decoder의 지연 프레임을 flush한 뒤 encoder·송신 컨테이너 자원을 정리한다.
- [x] T022 패킷 수신·송신, decode PTS 비정상 순서, inference/postprocess 콜백 오류 통계를 수집하고 1초마다 격리된 WebSocket 리포터로 전송한다.
- [x] T023 `tests/integration/test_pipeline_resilience.py`에서 opt-in 장시간 RTSP 송출, 입력 publish 중단 후 재연결, 사용자 모듈 hot reload를 자동 검증한다. (GPU·FFmpeg·RTSP publish 환경 필요)

## Bypass pipe type

- [x] T024 Add the `bypass` CLI pipe type and automatic stage disabling.
- [x] T025 Remux compressed input packets to RTSP without decoding or re-encoding.
- [x] T026 Add `bypass` to the Conductor UI and SQLite constraint, including migration for existing databases.
- [x] T027 Document bypass behavior and limitations in the feature and CLI specifications.
