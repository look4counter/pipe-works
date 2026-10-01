# ADR-002: Python Describes What, YAML Describes How

## Status

Accepted

## Context

The SDK must expose meaningful pipeline identity in Python while allowing
operational tuning outside code.

## Decision

Constructor arguments hold identity: RTSP URLs, model paths, action targets,
output targets, stream IDs, and stage names. YAML overrides behavior: timeout,
retry, reconnect, confidence, device, FP16, codec, bitrate, queue size, drop
policy, and batch wait.

## Alternatives Considered

- Put everything in YAML: deployable, but the Python pipeline becomes opaque.
- Put everything in Python: readable, but operational tuning requires code
  changes and encourages noisy `config.*` plumbing.

## Consequences

Configuration merging is required. Unknown settings should be observable, but
they should not prevent MVP execution.
