# Implementation Plan: Pipeline DSL SDK

## Goal

Build the MVP of a Python real-time video Pipeline SDK whose DSL reads like the
video flow. The first implementation proves public API shape, config override
semantics, stream identity, async actions, custom components, multi-stream batch
mapping, and multi-stage inference using deterministic in-memory components.

## Phasing

1. **MVP**: Fluent DSL, data models, default/YAML config, mock execution runtime, examples, tests.
2. **Multi-stream**: Stream declarations, batch collector semantics, demultiplexing, per-stream output.
3. **GPU Batch**: TensorRT/CUDA adapters, batching policies, device configuration, metrics.
4. **Advanced Pipeline**: Real RTSP/GStreamer, MediaMTX output, broker adapters, health/metrics exporters.

## Public API Decisions

- Pipeline declaration is fluent and ordered.
- Essential identity lives in Python constructor arguments.
- Behavior tuning lives in optional YAML keyed by component class name or instance name.
- Batch inference is explicit through `.batch_inference(...)`.
- Custom logic uses structural protocols and simple base classes for convenience.

## Runtime Design

- Compile the fluent declaration into an immutable `PipelineGraph`.
- Use stream-aware `PipelineContext` objects as the unit of processing.
- MVP main path runs deterministically in process.
- Actions are dispatched through a background `ActionDispatcher`.
- Outputs receive contexts after overlays/actions have been scheduled.
- Batch inference receives a list of contexts and must return one result per context.

## Configuration Design

Configuration merge order:

1. SDK defaults
2. YAML component type section
3. YAML component instance section
4. Explicit constructor options for identity values only

Unknown YAML sections are ignored but reported as warnings in the loaded config.

## Test Strategy

- DSL graph order and readability.
- Default configuration when no YAML is supplied.
- YAML override application.
- Single-stream execution with fake source/inference/output.
- Multi-stream batch identity preservation.
- Multi-stage inference result storage.
- Custom processor extension.
- Non-blocking action dispatch.

## ADRs

- ADR-001: Public DSL before runtime architecture.
- ADR-002: What in Python, How in YAML.
- ADR-003: Protocol-based component extension.
- ADR-004: Stream-aware context as runtime currency.
- ADR-005: Async action dispatcher separated from video path.
