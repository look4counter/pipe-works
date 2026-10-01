# Feature Specification: Command Harness Gates

**Feature Branch**: `004-command-harness-gates`

**Created**: 2026-10-01

**Status**: Draft

**Input**: Add command-backed verification gates so agent loops can run local quality checks and record evidence without a human gate.

## User Scenarios & Testing

### User Story 1 - Run Local Quality Commands as Harness Gates (Priority: P1)

An agent can configure a command gate, run it, and receive pass/fail evidence.

**Why this priority**: Autonomous development needs executable quality checks and durable evidence.

**Independent Test**: A command that exits zero produces passing evidence; a command that exits non-zero produces failing evidence.

**Acceptance Scenarios**:

1. **Given** a successful command, **When** the gate runs, **Then** it returns a passing `GateResult`.
2. **Given** a failing command, **When** the gate runs, **Then** it returns a failing `GateResult` with captured output.

## Requirements

- **FR-001**: Harness MUST support command-backed gates.
- **FR-002**: Command evidence MUST include command text, exit code, and output summary.
- **FR-003**: Commands MUST run with a timeout.
- **FR-004**: The SDK MUST provide default factory helpers for ruff and pytest gates.

## Success Criteria

- **SC-001**: Tests cover passing and failing command gates.
- **SC-002**: Existing SDK tests still pass.
