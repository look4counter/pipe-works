# 데이터 모델: 미디어 파이프라인

## 실행 파라미터

`PipelineArguments`는 불변 데이터 클래스이며 `parse_arguments()`가 생성한다.

| 필드 | 형식 | 현재 규칙 |
|---|---|---|
| `input_rtsp_url`, `output_rtsp_url` | 문자열 | 필수, `rtsp://` 접두사 |
| `input_rtsp_transport`, `output_rtsp_transport` | 문자열 | 필수, 값 허용 목록 미검증 |
| `pipe_type` | string | required, `nvidia` or `bypass` |
| `gpu_id` | 정수 | `--gpuid` 생략 시 0 |
| `fps` | 양의 정수 | 생략·null 시 30; encoder 설정에 전달 |
| `metadata_enabled`, `inference_enabled`, `postprocess_enabled` | boolean | 필수 `true` / `false` |
| 각 `*_path` | 문자열 또는 없음 | 단계 활성화 시 비어 있지 않은 경로 필수; 존재 여부는 로드 시 확인 |
| `inference_interval` | Positive integer | Defaults to 3; interval for the `infer` flag passed to the inference callback, which runs for every frame |
| `inference_frame` | 문자열 또는 없음 | `pytorch`만 허용; inference 활성화 시 필수 |
| `process_id` | 문자열 또는 없음 | Conductor 실행 식별용 선택값 |

## 프레임 파이프라인 객체

| 모델 | 필드 | 의미 |
|---|---|---|
| `ReceivePacket` | `video_stream`, `data`, `cuda_stream` | 선택된 PyAV 비디오 스트림, PyAV 패킷, 선택 CUDA stream |
| `FrameContext` | `video_stream`, `data`, `cuda_stream`, `pixel_format`, `codec`, `width`, `height`, `metadata`, `inference_result` | 디코딩 프레임, metadata 및 인코더 설정에 필요한 문맥 |
| `EncodedPacket` | `video_stream`, `data`, `time_base`, `codec`, `width`, `height` | 인코딩된 압축 바이트와 출력 stream 정보 |

`FrameContext.data` is an NVIDIA decoder `DecodedFrame`. When metadata is enabled, the latest `metadata()` value is attached to `FrameContext.metadata`. Inference is called for every frame as `on_frame(infer, parameters, frame)`; postprocess is called as `on_frame(parameters, frame)`. Both callbacks return a `FrameContext` containing metadata and inference results. `EncodedPacket` contains newly encoded bytes and output codec, resolution, and time base. Original packet PTS/DTS, keyframe flag, and extradata are not passed through; the sender sets PTS/DTS from output packet order.

## 사용자 모듈 상태

CLI의 공유 모듈 상태는 단계 이름을 키로 사용한다.

- `metadata`: `metadata()`가 반환한 객체
- `inference`: Python module providing `on_frame(infer, parameters, frame)`
- `postprocess`: `on_frame(parameters, frame)`를 가진 Python 모듈

활성화된 모듈은 실행 시작 시 로드된다. 감시 스레드는 파일 `st_mtime_ns`를 1초마다 확인해 변경된 모듈만 다시 불러온다. 새 파일의 import 또는 factory 호출이 실패하면 이전 객체를 유지하고 다음 확인에서 재시도한다. 모듈 교체는 공유 dict의 참조를 바꾸는 방식이다.

## Bypass packet contract

`ReceivePacket.data` is the demuxed PyAV packet from the first input video stream. In bypass mode the same packet object is assigned to the output stream created from the input stream template, then muxed without changing its compressed payload. The bypass path has no `FrameContext` or `EncodedPacket` stage. Empty packets are discarded in `receive`. A missing DTS is filled from PTS, synthesized from the previous successfully muxed DTS and configured FPS, or initialized to zero. DTS values not later than the previous successfully muxed packet are advanced by at least one frame period; PTS is shifted by the same correction when present. Each timestamp repair increments `anomalous`. Packet time bases are used to compare timestamps across packets.

Pipeline statistics contain five nonnegative integer counters (`received`, `sent`, `anomalous`, `inferenceFailed`, `postprocessFailed`) and nullable finite nonnegative `average_ms`. In NVIDIA mode, `average_ms` is the per-frame mean from decoder API call start through encoder API return, refreshed on one-second windows and aggregated in groups of up to `inference_interval` frames. It excludes packet wrapping and output/network send. Bypass mode leaves it null. `FrameContext.decode_started_at_ns` carries the monotonic timestamp used for this measurement.

`PipelineArguments.log_level` is a string constrained by the CLI to `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL`; its default is `INFO`.
