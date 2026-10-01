# 기능 명세: 미디어 파이프라인

**기능 경로**: `001-media-pipeline`  
**작성일**: 2026-09-23  
**상태**: NVIDIA RTSP 처리 경로, 사용자 모듈 재로드, 프로세스 통계 WebSocket 보고 구현; 실시간 종단 간 검증 및 일부 처리 계약 미완료

## 목적과 구현 범위

파이프라인은 RTSP 비디오를 수신하고 NVIDIA 하드웨어에서 디코드·인코드한 뒤 RTSP 출력으로 보낸다. 활성화된 inference와 postprocess 모듈은 프레임마다 호출한다. 활성화된 Python 모듈은 소스 파일의 수정 시간을 1초 간격으로 확인해 변경된 모듈을 다시 로드한다.

CPU processing is not supported. `--pipe-type` accepts `nvidia` and `bypass`; GPU ID defaults to 0. Bypass remuxes compressed video packets without decoding or re-encoding. Audio is out of scope.

## 사용자 시나리오 및 구현 상태

### 실행 설정 검증

CLI는 필수 입력·출력 RTSP URL, transport, NVIDIA pipe type, 단계별 활성화 설정을 검사한다. URL은 `rtsp://` 접두사만 검사하며 연결 가능성은 확인하지 않는다. 활성화된 사용자 모듈은 비어 있지 않은 경로가 필요하지만 파일 존재 여부는 파이프라인 시작 시 확인된다.

### RTSP 미디어 처리

수신기는 첫 비디오 스트림의 패킷을 전달한다. NVIDIA 디코더·인코더와 RTSP 송신기가 프레임 경로에 연결되어 있다. 수신 연결 또는 읽기에 실패하거나 입력 스트림이 끝나면 컨테이너를 닫고 3초 뒤 재연결한다. `av.open()`의 연결·읽기 timeout은 각각 5초다. stop event가 설정되면 현재 PyAV 읽기가 반환된 뒤 수신 루프를 종료한다.

### 사용자 모듈 처리

- metadata 모듈은 `metadata()`를 호출해 초기 값을 만들고, 파일이 바뀌면 새 모듈의 반환값으로 교체한다. metadata가 활성화되면 각 프레임 처리 직전에 최신 값을 `FrameContext.metadata`에 넣어 inference/postprocess에 전달한다.
- FRAME TYPE supports only `pytorch`. The inference module is called for every frame as `on_frame(infer, parameters, frame)`; `infer` is true only at the configured inference interval.
- postprocess 모듈은 inference 출력 또는 디코딩 프레임마다 `on_frame(parameters, frame)`을 호출한다.
- inference와 postprocess는 모듈 객체를 1초 감시 스레드로 교체한다. 새 파일 로드에 실패하면 직전 모듈을 유지하고 다음 검사에서 다시 시도한다.
- inference/postprocess 콜백 예외는 통계에 기록하고 해당 단계에 들어온 원본 프레임을 다음 단계로 전달한다. metadata 초기 로드나 reload가 실패하면 metadata 없이 프레임을 처리하며 watcher가 재시도한다.
- `--process-id`가 있으면 프로세스 전역 카운터를 1초마다 Conductor WebSocket으로 보낸다. 리포터는 전용 데몬 스레드에서 재연결을 수행해 미디어 처리 흐름을 기다리게 하지 않는다.

## CLI 계약

| 옵션 | 필수 여부 | 규칙 |
|---|---|---|
| `--input-rtsp-url` | 필수 | `rtsp://` 접두사 |
| `--input-rtsp-transport` | 필수 | 문자열; 허용 목록 검사는 없음 |
| `--output-rtsp-url` | 필수 | `rtsp://` 접두사 |
| `--output-rtsp-transport` | 필수 | 문자열; 허용 목록 검사는 없음 |
| `--pipe-type` | required | `nvidia` or `bypass` |
| `--gpuid` | 선택 | 정수; 기본값 0 |
| `--fps` | 선택 | 양의 정수; 기본값 30 |
| `--metadata-enabled` / `--inference-enabled` / `--postprocess-enabled` | 필수 | `true` 또는 `false` |
| 각 `--*-path` | 조건부 | 해당 단계 활성화 시 필요; 경로 존재 확인은 모듈 로드 시 수행 |
| `--inference-interval` | optional | Positive integer; defaults to 3. The inference callback receives `infer=true` on frame index 0 and every Nth frame thereafter. |
| `--inference-frame` | 조건부 | `pytorch`만 허용; inference 활성화 시 필수 |
| `--process-id` | 선택 | Conductor가 실행 식별 및 통계·로그 전송 대상을 식별하는 데 사용 |

## 처리 데이터 계약

1. `ReceivePacket`은 PyAV `VideoStream`과 PyAV 패킷을 보유한다.
2. NVIDIA 디코더는 패킷의 압축 바이트를 PyNvVideoCodec `PacketData`로 감싸 디코딩한다. 출력 `FrameContext`는 원본 stream, 디코딩 프레임, CUDA stream, pixel format, codec, 해상도, metadata와 inference 결과 슬롯을 보유한다.
3. inference 및 postprocess 콜백은 `FrameContext`를 받아 `FrameContext`를 반환한다.
4. NVIDIA 인코더는 `EncodedPacket`에 압축 바이트, codec, 해상도, time base와 원본 stream을 담는다.
5. 송신기는 출력 RTSP 컨테이너를 열고 인코더가 지정한 codec·해상도·time base로 stream을 설정한다. 출력 패킷 timestamp는 인코딩된 패킷 순번으로 새로 생성한다.

## 현재 제약 및 검증 범위

- When inference is enabled, call `on_frame(infer, parameters, frame)` for every decoded frame. `infer` is true on the first frame and every Nth frame thereafter, and false on intervening frames.
- ONNX FRAME TYPE은 지원하지 않으며 CLI와 웹 폼에서 선택할 수 없다.
- metadata는 활성화된 경우 각 프레임의 `FrameContext.metadata`를 통해 inference와 postprocess 단계에서 사용할 수 있다.
- 입력 packet의 timestamp, keyframe 표시, extradata는 출력으로 전달하지 않는다. 영상은 NVIDIA encoder에서 새로 인코딩되므로 원본 packet 속성의 보존은 요구하지 않는다.
- 송신기는 출력 인코딩 설정을 사용해 stream을 구성하고, packet 순번과 출력 time base로 PTS/DTS를 생성한다. 출력 codec·해상도·time base가 바뀌면 RTSP 출력을 다시 연다. DB 기반 NVIDIA/RTSP 종단 간 smoke test를 통과했다.
- 입력 stream 객체나 codec·해상도·extradata가 바뀌면 decoder를 다시 만들고, 출력 frame 형식이 바뀌면 기존 encoder를 flush한 뒤 재생성한다.
- stop event로 입력을 끝내면 decoder의 `Flush()` 결과를 다음 단계에 전달하고 encoder는 `EndEncode()`를 호출한다. 송신기는 남은 인코딩 패킷을 보낸 뒤 출력 컨테이너를 닫는다.
- 입력 수신과 출력 송신은 데이터 패킷 성공 기준으로 센다. decode 단계는 디코딩 프레임의 PTS가 이전 값 이하일 때 비정상 카운트를 올린다. inference/postprocess의 `on_frame` 예외는 각 실패 카운트에 반영하고 해당 단계의 입력 프레임을 그대로 전달한다.
- Pipeline statistics and logs use separate WebSocket reporting threads. By default they connect to the Conductor HTTP server on port `PIPE_WORKS_CONDUCTOR_PORT` (passed to child processes; defaults to 8000); `PIPE_WORKS_STATS_WS_URL` and `PIPE_WORKS_LOGS_WS_URL` override their respective URLs.
- 실행 시 `--process-id`가 있으면 Python logging 레코드를 bounded queue와 전용 WebSocket 스레드로 Conductor에 전달한다. 네트워크 송신은 미디어 처리 스레드를 기다리게 하지 않으며 큐가 가득 차면 오래된 로그부터 버린다.
- 정상 종료 결과 전달은 구현되지 않았다.
- 실제 GPU·FFmpeg·RTSP publish 환경이 있으면 `tests/integration/test_pipeline_resilience.py`로 장시간 스트림, 입력 재연결, 모듈 hot reload를 검증할 수 있다. 해당 테스트는 환경 변수가 없으면 skip된다.

## 요구사항 상태

- **FR-001**: Parse and validate CLI settings; accept `nvidia` and `bypass` pipe types. (Implemented)
- **FR-002**: RTSP 첫 비디오 스트림의 패킷을 수신하고 실패 또는 종료 후 재연결한다. (구현됨)
- **FR-003**: NVIDIA 디코드·인코드 및 RTSP 출력 경로를 연결하고 입력 설정 변경 시 decoder/encoder를 재구성한다. (구현 및 NVIDIA/RTSP 종단 간 smoke test 완료)
- **FR-004**: Call enabled inference `on_frame(infer, parameters, frame)` and postprocess `on_frame(parameters, frame)`. (Implemented; FRAME TYPE supports only `pytorch`.)
- **FR-005**: metadata·inference·postprocess 모듈을 파일 변경 시 재로드하고 metadata 활성 시 최신 값을 프레임 context로 전달한다. (구현됨)
- **FR-006**: 입력·출력 패킷 수, 비증가 decode PTS, inference/postprocess `on_frame` 예외를 프로세스 통계로 수집하고 1초마다 별도 스레드 WebSocket으로 보고한다. 네트워크 지연·장애는 미디어 처리를 막지 않아야 한다. (구현됨)


## Bypass pipe type

`--pipe-type bypass` forwards compressed video packets from the first input video stream to the output RTSP stream through remuxing. It does not decode or re-encode. Packet PTS, DTS, duration, keyframe flags, and codec extradata are retained where supported by the input/output containers. Metadata, inference, and postprocess are automatically disabled and their modules are not loaded. Audio is not forwarded. This remuxes packets between RTSP containers; it does not copy RTP network datagrams byte-for-byte.

## Source-level behavior and edge cases

- Input opens the RTSP URL with the selected transport and a 5-second open/read timeout. It uses only the first video stream and yields only packets whose size is greater than zero. EOF or an FFmpeg input error closes the container and retries after 3 seconds without a retry limit. A stop event is observed between reads; stopping can therefore wait for the current read timeout.
- `nvidia` supports H.264, HEVC, and H.265 input. It uses the selected GPU for NVDEC/NVENC and has no CPU fallback. A codec outside this set or GPU initialization failure terminates the pipeline.
- NVIDIA output uses encoder-generated packet bytes and creates PTS/DTS from an increasing packet counter with time base `1/fps`; input packet timestamps, keyframe flags, and extradata are not preserved. The output is reopened when encoded codec, dimensions, or time base changes.
- RTSP outputs set a 5-second FFmpeg network I/O timeout. Any exception while opening, initializing, or muxing an output closes the output, drops the failed frame or packet, continues consuming live input, and retries output creation every 3 seconds.
- In `bypass`, the output stream is created from the input stream template. A change to stream index, codec, dimensions, extradata, or input time base closes and reopens the output RTSP container. Missing DTS is filled from PTS, synthesized from the preceding successfully muxed DTS and configured FPS, or initialized to zero. DTS is compared in seconds using each packet's time base. A DTS not later than the previous successfully muxed DTS is advanced by at least one frame period, and PTS is shifted by the same correction when present. Each repair increments `anomalous`; the packet is still muxed if the output is available.
- `received` increments for every nonempty demuxed input packet. `sent` increments only after a packet is successfully muxed. In NVIDIA mode, `anomalous` increments when decoded frame PTS is equal to or lower than the preceding decoded PTS; decode-order tracking resets when decoder configuration changes. In bypass mode, it counts packets whose missing or non-increasing DTS required repair.
- `inference_interval` invokes inference on frame index 0 and every Nth frame thereafter. Inference and postprocess callback exceptions increment their respective counters and pass the original frame to the next stage. Metadata import/factory failures are tolerated at startup if the configured path can be stat-ed; a missing path and initial inference or postprocess module load failures stop startup. Failed hot reloads retain the last successfully loaded module and retry on the next poll.
- With `process_id`, cumulative statistics are sent once per second on a separate WebSocket thread. Pipeline logs use a bounded queue of 2048 records and a separate WebSocket thread. Both reports are best-effort and must not block media processing. Without `process_id`, these reporting threads are not started.

## Additional functional requirement

- **FR-007**: In bypass mode, skip empty input packets, preserve compressed payload bytes for packets that are muxed, and repair missing or non-increasing DTS monotonically while incrementing `anomalous` for each repair.

## Current implementation additions and corrections

- `--log-level` accepts `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL` and defaults to `INFO`. It sets the root Python logger threshold. The `websockets.client` logger remains at `WARNING` to suppress per-message payload logs even at `DEBUG`.
- NVIDIA mode publishes `average_ms`, the arithmetic mean per decoded frame from the start of the NVDEC `Decode`/`Flush` call to the return of the NVENC `Encode` call. It aggregates up to `inference_interval` frames at a time, includes a partial group at each timing window boundary, and refreshes over a one-second window. It excludes packet wrapping, RTSP mux/send, and network time. Bypass mode leaves it null.
- In bypass mode, absent DTS is filled from PTS, otherwise synthesized from the previous successfully muxed DTS using FPS, or initialized to zero. DTS is compared in seconds using each packet's time base. A DTS not later than the previous successfully muxed DTS is advanced by at least one frame period; PTS receives the same correction when present. Every repair increments `anomalous`; the packet is still sent if mux succeeds.
- **FR-008**: Support configurable Python log levels and report the NVIDIA per-frame decode-to-encode average as nullable `average_ms` statistics without blocking media processing.
