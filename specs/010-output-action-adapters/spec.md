# Feature Specification: Output and Action Adapters

**Feature Branch**: `010-output-action-adapters`

**Created**: 2026-10-01

**Status**: Draft

**Input**: Add production-shaped boundaries for HTTP actions, MQ publishing, and MediaMTX output without forcing external services in local tests.

## User Scenarios & Testing

### User Story 1 - Send Events Through Adapter Boundaries (Priority: P1)

An SDK user can configure HTTP/MQ actions and stream output descriptors while local tests remain deterministic.

## Requirements

- **FR-001**: HTTP action MUST be implementable with standard library dependencies.
- **FR-002**: MQ adapter MUST not require broker client dependency at import time.
- **FR-003**: MediaMTX output adapter MUST preserve output URL and stream identity.
- **FR-004**: Missing external dependencies MUST produce actionable errors.

## Success Criteria

- **SC-001**: Tests cover HTTP payload building.
- **SC-002**: Tests cover MQ missing dependency behavior.
- **SC-003**: Tests cover MediaMTX output descriptor behavior.
