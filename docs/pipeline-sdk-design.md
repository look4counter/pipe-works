# Pipeline SDK Design

## 1. Developer Experience Principles

The SDK user declares a video pipeline rather than writing a video program.
`pipeline.py` should be an executable architecture diagram: input, model,
overlays, actions, and output are visible from the fluent call chain.

Principles:

- Python DSL says **what** is connected.
- YAML says **how** it behaves.
- Safe defaults make YAML optional.
- Batch inference is explicit in the DSL because it changes execution meaning.
- Runtime internals stay hidden from normal users.
- Custom components fit naturally into the same chain.

## 2. Representative Use Cases

- Single RTSP stream -> inference -> overlay -> MQ/HTTP actions -> RTSP output.
- Nine camera streams -> shared batch inference -> per-stream overlays/outputs.
- Primary model -> crop/transform -> secondary model -> overlay/output.
- Domain-specific filtering via a custom processor.

## 3. Public API / DSL

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
```

## 4. Single-Stream Example

See [single_stream.py](../examples/single_stream.py).

## 5. Multi-Stream Example

See [multi_stream_batch.py](../examples/multi_stream_batch.py).

## 6. Batch Inference Example

Batch inference is declared with `.batch_inference(...)`, not hidden in YAML.
The runtime owns collection, inference call, and result mapping.

## 7. Multi-Stage Inference Example

See [multi_stage_inference.py](../examples/multi_stage_inference.py). Stage
names such as `primary` and `secondary` are preserved in context results.

## 8. Custom Component Extension

See [custom_component.py](../examples/custom_component.py). A custom component
implements `process(context) -> context` and can be inserted with `.process(...)`.

## 9. Runtime Architecture

The fluent declaration compiles into ordered steps. Runtime currency is a
`PipelineContext` holding one stream-aware `Frame`, inference results, overlays,
events, errors, and scratch data.

MVP runtime:

```text
Source/Streams -> Contexts -> Ordered Steps -> Outputs
                              └-> Actions via dispatcher
```

Future runtime:

```text
Source workers -> bounded frame queues -> batch collector -> inference worker
 -> demultiplexer -> per-stream processors -> output workers
```

## 10. Component Interfaces

Current MVP protocols:

- `SourceComponent.frames()`
- `InferenceComponent.infer(context, settings)`
- `BatchInferenceComponent.infer_batch(contexts, settings)`
- `ProcessorComponent.process(context)`
- `OverlayComponent.apply(context)`
- `ActionComponent.execute(context, settings)`
- `OutputComponent.write(context, settings)`

Protocols were chosen over a deep inheritance tree so user components can be
plain Python objects.

## 11. Frame / Context / Result Model

- `Frame`: `stream_id`, `image`, `timestamp`, `sequence`, metadata.
- `PipelineContext`: frame, stage results, overlays, events, errors, scratch data.
- `DetectionResult`: `stream_id`, `stage`, detections, frame sequence.

Stream identity is embedded in data models, not stored in a side table.

## 12. Concurrency / Async / Queue Architecture

MVP keeps the main path deterministic and dispatches actions through a background
dispatcher. Future slices add bounded queues between source, inference, actions,
and output workers.

## 13. GPU / TensorRT Execution Model

GPU execution is a later adapter. The public contract is already prepared:
`YoloInference("models/cobble.engine")` identifies the model, while YAML controls
device, FP16, confidence, max batch size, and batch wait.

## 14. Backpressure / Frame Drop / Batch Strategy

Defaults prefer real-time freshness over backlog growth:

- queue size is bounded
- default drop policy is `latest`
- batch inference has `max_batch_size` and `max_wait_ms`
- delayed streams should not block healthy streams indefinitely

## 15. Configuration Structure

Example:

```yaml
YoloInference:
  confidence: 0.7
  device: cuda:0
  fp16: true

BatchInference:
  max_batch_size: 9
  max_wait_ms: 20
  drop_policy: latest
```

Python constructors keep identity values such as URLs, model paths, topics, and
output targets.

## 16. Error Handling / Reconnect / Lifecycle

MVP records errors in context and metrics. Future runtime will model lifecycle
states: created, starting, running, draining, stopping, stopped, error, and
reconnecting.

## 17. Logging / Metrics / Observability

MVP result metrics include frames processed, action counts, outputs, and errors.
Future metrics add FPS, queue depth, dropped frames, latency percentiles,
reconnect attempts, and GPU memory.

## 18. Test Strategy

Current tests verify:

- DSL description readability
- YAML override behavior
- multi-stream batch identity preservation
- multi-stage inference result storage
- custom component processing
- non-blocking action scheduling

## 19. Package Structure

- `pipeworks.pipeline`: fluent DSL and MVP runtime
- `pipeworks.models`: public data models
- `pipeworks.components`: protocols and built-in MVP components
- `pipeworks.config`: defaults and YAML override loading
- `pipeworks.loop` / `pipeworks.harness`: agent engineering support layer

## 20. MVP Implementation

The MVP intentionally uses deterministic mock execution. Real RTSP, GPU, broker,
and MediaMTX adapters are next slices that must preserve the current DSL.

## Current Autonomous Slices

- Pipeline DSL MVP
- Realtime queue/drop policies
- Command-backed harness gates
- Pipeline lifecycle model
- Runtime metrics
- Local synthetic/file sources
- Developer-facing examples
- Optional GStreamer RTSP adapter boundary
- Optional YOLO/TensorRT inference adapter boundaries
- Optional HTTP/MQ/MediaMTX action/output adapter boundaries
