# 구현 계획 및 현황: 미디어 파이프라인

**기능 경로**: `001-media-pipeline` | **명세**: [spec.md](spec.md)

## 현재 구조

```text
src/pipeline/
├── arguments.py                 # CLI parameter model and validation for NVIDIA and bypass
├── cli.py                       # 모듈 로드·1초 hot reload, 단계 연결
├── receive.py                   # PyAV RTSP 입력, 패킷 yield, 3초 재연결
├── context.py                   # ReceivePacket, FrameContext, EncodedPacket
├── statistics.py                # 프로세스 전역 패킷·오류 카운터
├── stats_reporter.py             # 전용 스레드의 1초 WebSocket 리포터
├── log_reporter.py               # bounded queue를 사용하는 전용 로그 WebSocket 리포터
├── nvidia_pipe/decode.py        # PyNvVideoCodec 하드웨어 디코드
├── nvidia_pipe/encode.py        # PyNvVideoCodec 하드웨어 인코드
└── send.py                      # PyAV RTSP mux 출력
```

실행 흐름은 `receive → nvidia_decode → attach metadata(선택) → inference(on_frame, 선택) → postprocess(on_frame, 선택) → nvidia_encode → send`다. 사용자 모듈 감시자는 활성화된 모듈 파일을 1초 간격으로 확인하고 새 모듈을 공유 상태에 교체한다. metadata 활성 시 프레임마다 최신 `metadata()` 결과를 `FrameContext.metadata`에 담는다.

## 구현된 결정

- Python 3.11.9, PyAV, PyNvVideoCodec, PyTorch를 사용한다.
- 입력은 PyAV `av.open()`의 RTSP 입력이며 연결·읽기 timeout 각각 5초다. 첫 비디오 스트림만 사용한다.
- 입력 오류·EOF 후 컨테이너를 닫고 3초 간격으로 재시도한다. 재연결 횟수 제한은 없다.
- NVIDIA decoder/encoder와 CUDA stream을 사용한다. 자동 CPU fallback은 없다.
- 출력은 PyAV RTSP muxer로 전달하며 출력 transport를 옵션으로 넘긴다.
- 패킷 수신·송신, 비증가 디코드 PTS, 사용자 콜백 오류를 전역 카운터에 기록한다. 네트워크 보고는 전용 스레드에서 수행한다.
- Load user processing files as dynamic modules. The metadata module provides `metadata()`, inference provides `on_frame(infer, parameters, frame)`, and postprocess provides `on_frame(parameters, frame)`.
- `--pipe-type`의 유효값은 `nvidia` 하나이며 `--gpuid` 기본값은 0이다.

## 명세상 남은 구현·검증

1. [완료] metadata 값을 `FrameContext.metadata`로 inference/postprocess 콜백에 전달한다.
2. FRAME TYPE에서 pytorch만 허용하고 ONNX 선택값은 거부한다. (완료)
3. [x] Call the inference hook for every frame and pass actual inference eligibility through the `infer` argument.
4. [완료] 출력 인코더 설정과 새로 생성한 PTS/DTS를 사용해 mux하고 포맷 변경 시 출력 RTSP 연결을 다시 연다. 입력 packet 속성의 보존은 요구하지 않는다. 단위 테스트와 DB 기반 NVIDIA/RTSP smoke test를 통과했다.
5. [완료] 입력 stream 또는 codec·해상도·extradata 변경 뒤 decoder와 encoder를 재설정한다.
6. [완료] stop event가 receive 재시도를 중단하고, decoder flush 후 encoder 및 output 자원을 정리한다.
7. GPU가 필요한 NVIDIA 단위/통합 테스트 및 실제 RTSP 종단 간 재생 검증을 추가한다.
8. 통계 수집과 1초 WebSocket 보고를 구현했다. 네트워크 전송은 전용 스레드이며 Conductor와 UI는 별도 WebSocket으로 연결한다.

## 운영상 주의

`receive()`는 기본적으로 무한 재연결 iterator이며 stop event가 설정되면 종료한다. stop event는 현재 PyAV 읽기가 반환된 뒤 적용되며 RTSP read timeout까지 지연될 수 있다. inference/postprocess 콜백 예외는 통계에 반영한 뒤 해당 입력 프레임을 다음 단계로 전달한다. 통계와 로그 WebSocket 전송은 독립 스레드에서 재시도한다.


## Bypass path

The `bypass` flow is `receive -> send_bypass`. It applies the PyAV input stream template to the output stream and muxes each compressed packet without decoding or re-encoding. GPU initialization and user metadata, inference, and postprocess stages are skipped.

## Implemented bypass flow

When `pipe_type` is `bypass`, the pipeline branches after constructing `receive()` and sends its packet iterator directly to `send_bypass()`. The NVIDIA decoder, metadata, inference, postprocess, and encoder stages are skipped. The output RTSP container is reopened when the input stream configuration changes. Missing DTS values and non-increasing DTS values are repaired using packet time bases and the configured FPS, and each repair increments `anomalous`. Any mux exception is logged, the output is closed, and output creation is retried after three seconds while live input continues; the packet that failed to mux is dropped.
