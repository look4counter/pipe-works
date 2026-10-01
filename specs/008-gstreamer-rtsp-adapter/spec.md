# Feature Specification: GStreamer RTSP Adapter

**Feature Branch**: `008-gstreamer-rtsp-adapter`

**Created**: 2026-10-01

**Status**: Draft

**Input**: Add the first real RTSP adapter boundary without making GStreamer a mandatory dependency for local SDK tests.

## User Scenarios & Testing

### User Story 1 - Detect Missing GStreamer Clearly (Priority: P1)

An SDK user can import the adapter module without GStreamer installed and receives a clear runtime error only when trying to use the real adapter.

**Acceptance Scenarios**:

1. **Given** GStreamer bindings are unavailable, **When** adapter availability is checked, **Then** the SDK reports unavailable.
2. **Given** GStreamer bindings are unavailable, **When** real frames are requested, **Then** the SDK raises an actionable dependency error.

## Requirements

- **FR-001**: Adapter imports MUST NOT require GStreamer at import time.
- **FR-002**: Adapter MUST expose availability status.
- **FR-003**: Adapter MUST expose a readable pipeline descriptor.
- **FR-004**: Adapter MUST preserve stream identity in produced frames.

## Success Criteria

- **SC-001**: Tests pass without GStreamer installed.
- **SC-002**: Missing dependency error includes installation guidance.
