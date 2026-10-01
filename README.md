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

## Layout

- `src/pipeworks/core`: current LOOP/harness foundation; later SDK domain contracts
- `src/pipeworks/pipeline.py`: fluent Pipeline DSL and MVP runtime
- `src/pipeworks/components.py`: component protocols and built-in MVP components
- `src/pipeworks/models.py`: stream-aware frame/context/result models
- `src/pipeworks/config.py`: default and YAML runtime configuration
- `src/pipeworks/loop`: AI Agent LOOP orchestration for development automation
- `src/pipeworks/harness`: quality gates used to verify SDK slices
- `src/pipeworks/adapters`: local reference adapters and future runtime adapters
- `specs/001-agent-sdk-foundation`: first accepted feature slice
- `specs/002-pipeline-dsl-sdk`: Pipeline DSL SDK feature specification
- `docs`: product architecture, loop protocol, and quality gates

Design details: [docs/pipeline-sdk-design.md](docs/pipeline-sdk-design.md)
