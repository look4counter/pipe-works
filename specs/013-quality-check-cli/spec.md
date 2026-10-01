# Feature Specification: Quality Check CLI

**Feature Branch**: `013-quality-check-cli`

**Created**: 2026-10-01

**Status**: Draft

**Input**: Add a one-command local quality gate so autonomous agent loops can verify the SDK without asking a human.

## User Scenarios & Testing

### User Story 1 - Run SDK Quality Gates Locally (Priority: P1)

An SDK maintainer or agent can run one command to execute curated lint and test gates.

## Requirements

- **FR-001**: CLI MUST provide `pipeworks check`.
- **FR-002**: Check command MUST run ruff and pytest command gates.
- **FR-003**: Check command MUST return non-zero if any gate fails.
- **FR-004**: Check command MUST print evidence summaries.

## Success Criteria

- **SC-001**: CLI tests verify `check` invokes gates and returns success when gates pass.
