# ADR-001: Public DSL Before Runtime Architecture

## Status

Accepted

## Context

The SDK's primary quality bar is whether a developer can understand a video
pipeline by opening `pipeline.py`. Runtime choices such as GStreamer, FFmpeg,
TensorRT, queues, workers, and reconnect loops are important, but they must not
drive the Public API shape.

## Decision

Design the fluent Pipeline DSL first, then design runtime internals to satisfy
that DSL. The MVP API exposes ordered video concepts: `source`, `streams`,
`inference`, `batch_inference`, `transform`, `process`, `overlay`, `action`,
and `output`.

## Alternatives Considered

- Runtime-first API: easier to implement but leaks queues, workers, and
  demuxing concepts into user code.
- YAML-first API: operationally flexible but hides source/model/output identity
  from the code that should act as the architecture diagram.

## Consequences

The runtime may need adapter and compiler layers, but user code remains readable.
Future runtime optimizations must preserve DSL clarity.
