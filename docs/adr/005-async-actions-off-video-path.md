# ADR-005: Async Actions Off the Video Path

## Status

Accepted

## Context

HTTP calls, MQ publishes, SVG sends, and other actions can be slow or fail. They
must not block inference, overlay, encoding, or output in the common path.

## Decision

Actions are scheduled through an `ActionDispatcher` with bounded worker
semantics. MVP uses a background thread executor; future runtimes may use
asyncio, process pools, or broker-native producers behind the same contract.

## Alternatives Considered

- Synchronous actions: simpler but can stall real-time video.
- Force users to manage async queues: flexible but leaks internals.

## Consequences

Actions become eventually completed side effects. Tests and metrics must expose
scheduled/completed/failed counts.
