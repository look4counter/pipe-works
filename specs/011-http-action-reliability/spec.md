# Feature Specification: HTTP Action Reliability

**Feature Branch**: `011-http-action-reliability`

**Created**: 2026-10-01

**Status**: Draft

**Input**: Continue autonomous SDK implementation by proving real HTTP action delivery and retry behavior without external services.

## User Scenarios & Testing

### User Story 1 - Deliver Action Payloads Over HTTP (Priority: P1)

An SDK user can configure an HTTP action and trust that detection context is serialized and sent as JSON.

**Acceptance Scenarios**:

1. **Given** a local HTTP endpoint, **When** `HttpPostAction` executes, **Then** the endpoint receives stream identity, frame sequence, and detection data.
2. **Given** a transient HTTP failure, **When** retry is configured, **Then** the action retries and succeeds if a later attempt succeeds.

## Requirements

- **FR-001**: HTTP action MUST serialize stream identity, frame sequence, and detections.
- **FR-002**: HTTP action MUST honor `timeout` setting.
- **FR-003**: HTTP action MUST honor `retry` setting.
- **FR-004**: Tests MUST use a local server, not an external network service.

## Success Criteria

- **SC-001**: Local server integration test receives expected JSON payload.
- **SC-002**: Retry test proves at least one failed attempt can be recovered.
