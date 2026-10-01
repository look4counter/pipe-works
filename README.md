# Pipe Works

Pipe Works is being restarted as an agent-driven real-time video pipeline SDK.
The product SDK is for ingesting live streams, running AI inference, applying
bounded backpressure, publishing events, and exposing metrics. AI Agent LOOP
engineering and the harness are the way we build and verify the SDK with minimal
human gates; they are not the product domain itself.

The old media pipeline implementation has been preserved as `src_bak`, and the
old specs have been preserved as `specs_bak`.

## Current Slice

The current slice implements the first working version of the public Pipeline
DSL and a deterministic MVP runtime:

- readable fluent pipeline declarations
- single-stream execution with mock/descriptor components
- multi-stream batch inference semantics
- stream identity preservation
- multi-stage inference result storage
- YAML behavior overrides
- async action dispatch
- custom processors
- realtime queue/drop and batch collection policies
- pipeline lifecycle state
- runtime metrics
- optional adapter boundaries for GStreamer RTSP, YOLO/TensorRT, HTTP, MQ, and MediaMTX

Example:

```python
pipeline = (
    Pipeline("cobble-detection")
    .source(RTSPSource("rtsp://camera/main"))
    .inference(YoloInference("models/cobble.engine"))
    .overlay(StaticBoxOverlay())
    .overlay(DetectionBoxOverlay())
    .action(SvgSendAction("http://server/api/svg"))
    .action(MQPublishAction("cobble.detected"))
    .output(RTSPPublisher("rtsp://mediamtx/cobble"))
)

pipeline.run()
```

## Run

```powershell
python -m pytest -q
python -m pipeworks.cli --once
```

## Examples

Developer-facing examples live in [examples](examples):

- [01_single_stream_rtsp_style.py](examples/01_single_stream_rtsp_style.py): RTSP-shaped single-stream pipeline
- [02_multistream_batch.py](examples/02_multistream_batch.py): 9-channel batch inference declaration
- [03_multistage_inference.py](examples/03_multistage_inference.py): primary inference, crop, secondary inference
- [04_custom_component.py](examples/04_custom_component.py): custom domain processor
- [05_local_synthetic_config.py](examples/05_local_synthetic_config.py): local synthetic source with YAML behavior overrides

## Layout

- `src/pipeworks/core`: current LOOP/harness foundation; later SDK domain contracts
- `src/pipeworks/pipeline.py`: fluent Pipeline DSL and MVP runtime
- `src/pipeworks/components.py`: component protocols and built-in MVP components
- `src/pipeworks/models.py`: stream-aware frame/context/result models
- `src/pipeworks/config.py`: default and YAML runtime configuration
- `src/pipeworks/runtime.py`: realtime queue/drop and batch collection policies
- `src/pipeworks/lifecycle.py`: pipeline lifecycle state model
- `src/pipeworks/adapters`: optional runtime adapter boundaries
- `src/pipeworks/loop`: AI Agent LOOP orchestration for development automation
- `src/pipeworks/harness`: quality gates used to verify SDK slices
- `specs/001-agent-sdk-foundation`: first accepted feature slice
- `specs/002-pipeline-dsl-sdk`: Pipeline DSL SDK feature specification
- `specs/003-*` and later: autonomous implementation slices
- `docs`: product architecture, loop protocol, and quality gates

Design details: [docs/pipeline-sdk-design.md](docs/pipeline-sdk-design.md)
