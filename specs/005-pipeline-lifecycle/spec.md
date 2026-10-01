# Feature Specification: Pipeline Lifecycle

**Feature Branch**: `005-pipeline-lifecycle`

**Created**: 2026-10-01

**Status**: Draft

**Input**: Add explicit pipeline lifecycle states so runtime state is observable and future worker/reconnect execution has a stable state contract.

## User Scenarios & Testing

### User Story 1 - Observe Pipeline State (Priority: P1)

An SDK user can inspect a pipeline state before and after execution without knowing worker internals.

**Acceptance Scenarios**:

1. **Given** a newly created pipeline, **When** state is inspected, **Then** it is `created`.
2. **Given** a successful run, **When** state is inspected, **Then** it is `stopped`.
3. **Given** an execution error, **When** state is inspected, **Then** it is `error`.

## Requirements

- **FR-001**: Pipeline MUST expose lifecycle state.
- **FR-002**: Lifecycle MUST support `created`, `starting`, `running`, `draining`, `stopped`, `error`, and `reconnecting`.
- **FR-003**: Invalid state transitions MUST fail fast.
- **FR-004**: Pipeline results MUST include final lifecycle state.

## Success Criteria

- **SC-001**: Tests verify successful state transitions.
- **SC-002**: Tests verify failed runs enter `error`.
