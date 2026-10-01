# CLI 및 사용자 모듈 계약: 미디어 파이프라인

구현 기준: `src/pipeline/arguments.py`, `src/pipeline/cli.py`.

## CLI

| 파라미터 | 필수 | 현재 규칙 |
|---|---:|---|
| `--input-rtsp-url` | 예 | `rtsp://`로 시작 |
| `--input-rtsp-transport` | 예 | 임의 문자열, 허용 목록 없음 |
| `--output-rtsp-url` | 예 | `rtsp://`로 시작 |
| `--output-rtsp-transport` | 예 | 임의 문자열, 허용 목록 없음 |
| `--pipe-type` | required | `nvidia` or `bypass` |
| `--gpuid` | 아니오 | 정수, 기본값 0 |
| `--fps` | 아니오 | 양의 정수, 기본값 30 |
| `--metadata-enabled` | 예 | `true` / `false` |
| `--metadata-path` | 조건부 | metadata 활성화 시 비어 있지 않아야 함 |
| `--inference-enabled` | 예 | `true` / `false` |
| `--inference-path` | 조건부 | inference 활성화 시 비어 있지 않아야 함 |
| `--inference-interval` | 아니오 | 양의 정수, 기본값 3; 첫 프레임 및 이후 N프레임 간격으로 inference 콜백을 호출 |
| `--inference-frame` | 조건부 | `pytorch`만 허용; inference 활성화 시 필수 |
| `--postprocess-enabled` | 예 | `true` / `false` |
| `--postprocess-path` | 조건부 | postprocess 활성화 시 비어 있지 않아야 함 |
| `--process-id` | 아니오 | Conductor가 전달하는 문자열 |

URL 접두사와 필수 필드만 파싱 단계에서 검사한다. URL 도달성, transport 값, 경로 파일 존재 여부는 이 단계에서 확인하지 않는다.

## Python 모듈

- **metadata**: 파일은 `metadata()` 함수를 제공하고 metadata 객체를 반환한다. metadata가 활성화되면 최신 반환값을 각 `FrameContext.metadata`에 설정하며 inference/postprocess 콜백은 `frame.metadata`로 접근한다. 파일 reload 후에는 다음 프레임부터 새 값을 사용한다.
- **inference**: Provide `on_frame(infer, parameters, frame)` and return each `FrameContext`. `infer` is true on interval frames; FRAME TYPE supports only `pytorch`.
- **postprocess**: `on_frame(parameters, frame)`를 제공하고 각 입력 `FrameContext`를 반환한다. inference 결과 다음 단계에서 호출된다.
- 활성화된 세 모듈은 파일 수정 시간을 1초마다 확인한다. 성공적으로 로드된 새 값은 다음 프레임부터 사용한다. 로드 실패 시 기존 값을 유지하고 재시도한다.
- inference/postprocess의 `on_frame()` 예외는 실패 통계에 기록하고 입력 프레임을 그대로 반환한다. metadata 초기 로드 실패 시 metadata 없이 진행하고, reload 실패 시 이전 metadata 값을 유지하며 재시도한다.

## 미디어 입출력

입력은 첫 PyAV 비디오 스트림의 패킷이며, NVIDIA decoder에 전달할 때 PyNvVideoCodec `PacketData`로 바꾼다. 출력은 NVIDIA encoder 바이트를 PyAV RTSP muxer에 전달한다. 입력 packet의 timestamp·keyframe·extradata는 출력에 보존하지 않는다. 송신기는 출력 time base와 packet 순번으로 PTS/DTS를 생성한다.

## Bypass CLI behavior

`--pipe-type` accepts `nvidia` or `bypass`. All three `--metadata-enabled`, `--inference-enabled`, and `--postprocess-enabled` boolean options remain required by the parser. For `bypass`, their supplied values are forced to false before the pipeline is assembled; module paths are not required or loaded. `--inference-frame` is not required in bypass mode. GPU ID and FPS retain their parser defaults but do not control bypass packet remuxing.

Current additional CLI and telemetry behavior: `--log-level` accepts `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL` and defaults to `INFO`. It sets the root Python logger threshold; `websockets.client` is held at `WARNING` to suppress per-message payload logs at `DEBUG`. NVIDIA statistics include nullable `average_ms`: the mean decode-call-start to encode-call-return duration per decoded frame, refreshed over one-second windows and grouped in batches of up to `inference_interval` frames. This excludes RTSP mux/send and network time; bypass leaves it null.
