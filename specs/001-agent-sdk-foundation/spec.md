# Feature: Agent-Driven SDK Foundation

## Intent

Pipe Works restarts as a real-time video pipeline SDK developed through an AI
Agent LOOP process. The foundation makes engineering loops explicit,
measurable, and replayable so agents can build the media SDK with minimal human
gates.

## Goals

- Provide a LOOP engine: select task, perform work, run harness, record evidence.
- Keep the product SDK focused on streams, frames, inference, events, and metrics.
- Separate media SDK contracts from runtime adapters such as GStreamer, YOLO, TensorRT, and brokers.
- Treat specs, decisions, tasks, and evidence as first-class artifacts.
- Keep human gates for irreversible decisions, credentials, production-impacting operations, or conflicting acceptance criteria.

## Non-Goals

- Real RTSP/GStreamer integration in the first slice.
- Real model-provider integration in the first slice.
- Replacing human approval for breaking public API changes.

## Requirements

- `SDK-001`: The loop engine MUST select the highest-priority unblocked task.
- `SDK-002`: The loop engine MUST run implementation and verification through ports.
- `SDK-003`: The harness MUST emit durable evidence for every gate.
- `SDK-004`: Failed implementation evidence or failed gates MUST block the current loop.
- `SDK-005`: The engineering layer MUST not depend on a specific LLM, issue tracker, CI provider, or runtime.
- `SDK-006`: The product SDK direction MUST remain real-time video pipeline oriented.
- `SDK-007`: Future product slices MUST define media contracts before binding to runtime adapters.

## Acceptance Criteria

- A local in-memory harness can complete one task and record evidence.
- A task with unmet dependencies is not selected.
- Default tests exercise the new LOOP foundation without requiring old media pipeline modules.
- Documentation clearly distinguishes the video pipeline SDK from the AI Agent engineering layer.
