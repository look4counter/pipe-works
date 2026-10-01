# ADR-004: Stream-Aware Context as Runtime Currency

## Status

Accepted

## Context

Multi-stream batch inference must map every result back to its source stream.
Users should not write batch collector or demultiplexer logic.

## Decision

Every frame and processing context carries `stream_id`, timestamp, and sequence.
Inference results carry both `stream_id` and `stage`. Batch inference operates
on lists of contexts and returns one result per context.

## Alternatives Considered

- Keep stream identity in side tables: efficient in some runtimes but fragile.
- Leave demultiplexing to users: exposes internal complexity and violates the
  DSL goal.

## Consequences

Context objects become the stable boundary between components. This slightly
increases object metadata but greatly simplifies correctness.
