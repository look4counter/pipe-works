# Feature Specification: Runtime Metrics

**Feature Branch**: `006-runtime-metrics`

**Created**: 2026-10-01

**Status**: Draft

**Input**: Extend runtime metrics so SDK users and agents can observe pipeline execution, queue behavior, batch behavior, and action latency.

## User Scenarios & Testing

### User Story 1 - Inspect Pipeline Runtime Metrics (Priority: P1)

An SDK user can inspect execution duration, effective FPS, queue drops, batch size, action counts, and action latency after a run.

**Acceptance Scenarios**:

1. **Given** a successful run, **When** metrics are inspected, **Then** duration and effective FPS are present.
2. **Given** a slow action, **When** metrics are inspected after waiting for actions, **Then** action latency is recorded.

## Requirements

- **FR-001**: Metrics MUST include run duration in milliseconds.
- **FR-002**: Metrics MUST include effective FPS.
- **FR-003**: Metrics MUST include queue dropped count and max depth.
- **FR-004**: Metrics MUST include batch size.
- **FR-005**: Metrics MUST include action latency summary.

## Success Criteria

- **SC-001**: Tests verify positive duration and FPS.
- **SC-002**: Tests verify action latency is recorded.
