# Plan: Agent-Driven SDK Foundation

## Architecture

- Product SDK direction: real-time video pipeline contracts for source, frame, queue, inference, event publishing, pipeline lifecycle, and metrics.
- Engineering foundation: LOOP orchestration, harness gates, evidence records, and agent/tool adapters.
- Runtime adapters come after contracts: GStreamer, YOLO, TensorRT, MediaMTX, MQTT/Kafka/RabbitMQ.

## Loop Strategy

1. Select highest-value unblocked task.
2. Execute with an agent adapter.
3. Verify with a harness.
4. Record evidence.
5. Continue only when gates pass.

## Harness Strategy

Start with deterministic local gates. Add command gates later for lint, typecheck,
unit tests, contract tests, benchmarks, and documentation drift checks.

Product harness gates must eventually cover:

- bounded queue/drop policy behavior
- non-blocking event dispatch
- inference timeout/failure isolation
- pipeline lifecycle and graceful shutdown
- metrics and evidence capture

## Human Gate Policy

Human gates are reserved for credentials, destructive changes, production
deployments, breaking public API changes, and contradictions in accepted specs.
