# Product Vision

Pipe Works is a Python SDK for real-time video processing pipelines.

The SDK should let an application assemble camera or file sources, bounded frame
queues, AI inference providers, event publishers, optional stream sinks, and
observability into reliable pipelines.

## What We Are Building

- A source abstraction for RTSP, files, synthetic streams, and tests.
- A frame and metadata contract owned by the SDK.
- Bounded queues with explicit freshness and drop policies.
- Inference provider adapters for fake/local/remote AI models.
- Async event publishing so slow hooks cannot block the media path.
- Pipeline lifecycle controls: start, stop, drain, reconnect, error.
- Metrics for FPS, queue depth, drops, latency, errors, and health.
- Harnesses that prove behavior before a slice is accepted.

## What AI Agents Do Here

AI Agents implement and verify SDK slices through a LOOP protocol:

```text
spec -> task -> implementation -> harness evidence -> decision/doc update
```

The agent layer reduces human gates. It does not replace the SDK product domain.

## Human Gates

Humans should only be required for:

- credentials and external accounts
- destructive operations
- production-impacting deployments
- breaking public API changes
- contradictory or ambiguous acceptance criteria
- architecture decisions whose evidence is inconclusive after the retry budget
