# Feature Specification: Examples Execution Harness

**Feature Branch**: `012-examples-execution-harness`

**Created**: 2026-10-01

**Status**: Draft

**Input**: Keep developer-facing examples executable as SDK contracts evolve.

## User Scenarios & Testing

### User Story 1 - Prevent Broken Examples (Priority: P1)

An SDK maintainer can run tests and know the developer-facing examples still execute.

## Requirements

- **FR-001**: Harness MUST execute all curated developer examples.
- **FR-002**: Harness MUST run examples in subprocesses to match user execution.
- **FR-003**: Harness MUST not execute legacy backup examples.

## Success Criteria

- **SC-001**: Test suite fails if any curated example exits non-zero.
