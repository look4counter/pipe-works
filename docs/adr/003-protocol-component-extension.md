# ADR-003: Protocol-Based Component Extension

## Status

Accepted

## Context

Users need custom processors, overlays, actions, sources, and outputs without
editing SDK internals.

## Decision

Use structural protocols for component contracts and provide small convenience
base classes. Users can implement the required methods directly or inherit from
base classes for names/config helpers.

## Alternatives Considered

- Deep inheritance tree: discoverable but rigid and harder to compose.
- Free functions only: concise but poor for reusable configured components.

## Consequences

The runtime can accept user-defined classes with minimal coupling. Type checks
and tests must cover protocol behavior rather than exact subclasses.
