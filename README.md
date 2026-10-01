# Pipe Works

Pipe Works is being restarted as an agent-driven real-time video pipeline SDK.
The product SDK is for ingesting live streams, running AI inference, applying
bounded backpressure, publishing events, and exposing metrics. AI Agent LOOP
engineering and the harness are the way we build and verify the SDK with minimal
human gates; they are not the product domain itself.

The old media pipeline implementation has been preserved as `src_bak`, and the
old specs have been preserved as `specs_bak`.

## Current Slice

The first slice proves the engineering foundation that future media components
must pass through:

- task selection
- agent execution through a port for automated implementation loops
- harness verification for SDK quality gates
- evidence recording
- minimal human-gate policy

The next product slice should introduce the SDK contracts for:

- `Source`: RTSP/file/mock frame sources
- `FrameQueue`: bounded queues and drop policies
- `InferenceProvider`: YOLO/TensorRT/remote inference adapters
- `EventPublisher`: non-blocking detection/event dispatch
- `Pipeline`: single-camera lifecycle, metrics, and failure isolation

## Run

```powershell
python -m pytest -q
python -m pipeworks.cli --once
```

## Layout

- `src/pipeworks/core`: current LOOP/harness foundation; later SDK domain contracts
- `src/pipeworks/loop`: AI Agent LOOP orchestration for development automation
- `src/pipeworks/harness`: quality gates used to verify SDK slices
- `src/pipeworks/adapters`: local reference adapters and future runtime adapters
- `specs/001-agent-sdk-foundation`: first accepted feature slice
- `docs`: product architecture, loop protocol, and quality gates
