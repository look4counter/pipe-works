# 빠른 검증: 미디어 파이프라인

## CLI 설정 확인

1. Python 3.11.9와 프로젝트 의존성을 준비하고, 프로젝트의 Python 모듈 경로에서 `python -m pipeline.cli`를 실행한다.
2. Configure required RTSP URLs and transports. Use `--pipe-type nvidia` for GPU processing or `--pipe-type bypass` to remux compressed packets without decoding or re-encoding. In bypass mode metadata, inference, and postprocess are automatically disabled.
3. 활성화된 각 사용자 모듈에 경로를 주고 inference 활성화 시 `--inference-frame pytorch`를 지정한다.
4. 잘못된 URL 접두사, pipe type, boolean, 양수가 아닌 FPS·inference interval, 누락된 활성 모듈 경로가 거부되는지 확인한다.

## NVIDIA RTSP 경로 확인

1. NVIDIA 드라이버와 호환 GPU가 있는 환경에서 유효한 입력 RTSP와 쓰기 가능한 출력 RTSP를 지정한다.
2. Provide `metadata()` in the metadata module, `on_frame(infer, parameters, frame)` in the inference module, and `on_frame(parameters, frame)` in the postprocess module.
3. 파이프라인 실행 후 입력 비디오가 출력 RTSP에서 재생되는지 확인한다. 이 단계는 실시간 RTSP 서버·GPU가 필요하며 단위 테스트로 대체되지 않는다.
4. 실행 중 사용자 모듈 파일을 변경하고 1초 감시 간격 후 다음 프레임에 새 모듈이 적용되는지 로그 또는 콜백 결과로 확인한다.

장시간 스트림·재연결·모듈 hot reload 통합 검증은 `PIPE_WORKS_TEST_PUBLISH_RTSP_URL` (테스트가 publish 가능한 RTSP 경로), `PIPE_WORKS_TEST_OUTPUT_RTSP_URL` (출력 경로), 선택적인 `PIPE_WORKS_TEST_GPU_ID`, `PIPE_WORKS_TEST_LONG_STREAM_SECONDS`, `PIPE_WORKS_TEST_RECONNECT_PAUSE_SECONDS`를 설정하고 `pytest tests/integration/test_pipeline_resilience.py`로 실행한다. FFmpeg 실행 파일이 필요하며 `PIPE_WORKS_TEST_FFMPEG`로 경로를 지정할 수 있다.

## 현재 제한

- FRAME TYPE은 현재 `pytorch`만 지원한다.
- The inference hook runs on every frame. Its `infer` argument is true on the first frame and every `inference_interval` frames thereafter, and false on other frames.
- metadata가 활성화되면 최신 반환값이 각 프레임의 `frame.metadata`에 전달되며 inference/postprocess에서 사용할 수 있다.
- 출력 timestamp는 원본 packet에서 가져오지 않고 packet 순번과 설정 FPS를 기준으로 새로 만든다. 원본 keyframe·extradata 보존은 요구하지 않는다.
- 입력 연결이 재생성되거나 codec·해상도가 바뀌면 decoder와 encoder를 재구성하고, 출력 형식이 바뀌면 RTSP 출력을 다시 연다. DB 설정 또는 RTSP 환경 변수로 opt-in 종단 간 테스트를 실행할 수 있다.
