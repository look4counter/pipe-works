# Pipe Works Architecture

Pipe Works is a real-time video pipeline SDK built with an AI Agent driven
engineering process. The SDK domain is media and AI inference. The LOOP engine
and harness are internal engineering infrastructure that let agents implement,
verify, and document SDK slices with fewer human gates.

Reference direction comes from `C:\workspace\github\visionflow-sdk\docs`:
GStreamer-style media runtime boundaries, per-camera pipeline isolation,
bounded queues, freshness-aware frame dropping, SDK-owned metadata contracts,
async event dispatch, and observability.

## Product SDK

The SDK should expose stable contracts for:

- `Source`: RTSP, file, synthetic, and mock sources.
- `Frame`: timestamped image/video payload plus source metadata.
- `FrameQueue`: bounded queue with `drop_oldest`, `drop_newest`, `sample`, and `block`.
- `InferenceProvider`: local or remote model adapters.
- `DetectionResult`: SDK-owned normalized metadata.
- `EventPublisher`: non-blocking event fanout with timeout and drop metrics.
- `Pipeline`: lifecycle, failure isolation, graceful shutdown, and metrics.

## Engineering Layer

- `pipeworks.loop`: chooses unblocked work, runs agent adapters, invokes harnesses.
- `pipeworks.harness`: lint/type/test/contract/failure/performance gates.
- `pipeworks.adapters`: connects agents, tools, CI, stores, and future runtime adapters.

These pieces are support systems. They should not obscure the media SDK API.

## Principles Adopted

- Core SDK contracts stay vendor-neutral.
- Ports and adapters isolate GStreamer, YOLO, TensorRT, brokers, and stores.
- Media plane and event plane are separated.
- Queues, workers, retries, retained frames, and event buffers are bounded.
- Real-time behavior prefers freshness over backlog accumulation.
- Camera and plugin failures have explicit blast-radius boundaries.
- Lifecycle states are observable: start, stop, drain, reconnect, error.
- Metadata belongs to the SDK contract rather than a model vendor format.
- Observability is a first-class behavior, not an optional add-on.
- Every completed agent loop leaves evidence.
- Human gates are minimized and reserved for irreversible or ambiguous decisions.

## Next Design Decisions

- ADR-001: Product media runtime boundary for the restarted SDK.
- ADR-002: SDK metadata contract.
- ADR-003: Frame queue and freshness policy.
- ADR-004: Hook/event execution model.
- ADR-005: Evidence store format for agent loops.
- ADR-006: Command harness semantics and retry budget.
