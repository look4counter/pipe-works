# Feature Specification: Init Example CLI

**Feature Branch**: `015-init-example-cli`

**Created**: 2026-10-01

**Status**: Draft

**Input**: Add a CLI command that creates starter pipeline files for SDK users.

## User Scenarios & Testing

### User Story 1 - Bootstrap a Pipeline Project (Priority: P1)

An SDK user can run a command and receive a starter `pipeline.py` and `pipeworks.yaml`.

## Requirements

- **FR-001**: CLI MUST provide `--init-example <directory>`.
- **FR-002**: Generated files MUST be runnable without external services.
- **FR-003**: Generated pipeline MUST preserve readable DSL style.
- **FR-004**: Command MUST avoid overwriting existing files unless explicitly supported later.

## Success Criteria

- **SC-001**: Test verifies generated files exist.
- **SC-002**: Test executes generated `pipeline.py`.
