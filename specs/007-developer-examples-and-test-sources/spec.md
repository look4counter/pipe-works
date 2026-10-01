# Feature Specification: Developer Examples and Test Sources

**Feature Branch**: `007-developer-examples-and-test-sources`

**Created**: 2026-10-01

**Status**: Draft

**Input**: Add developer-facing examples and local test sources so users can learn the SDK without RTSP/GPU infrastructure.

## User Scenarios & Testing

### User Story 1 - Learn SDK by Example (Priority: P1)

An SDK user can open examples and see common pipeline types.

**Acceptance Scenarios**:

1. **Given** the examples folder, **When** a developer opens it, **Then** at least five pipeline types are represented.
2. **Given** no camera or GPU, **When** local examples run, **Then** they complete with synthetic or file sources.

## Requirements

- **FR-001**: SDK MUST provide a synthetic source.
- **FR-002**: SDK MUST provide a file descriptor source for local examples.
- **FR-003**: Examples MUST cover single-stream, multi-stream batch, multi-stage inference, custom component, and YAML configuration/action fanout.
- **FR-004**: Examples MUST keep the Pipeline DSL readable.

## Success Criteria

- **SC-001**: At least five example source files exist.
- **SC-002**: Local examples execute without external services.
