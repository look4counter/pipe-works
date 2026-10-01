# Feature Specification: Pipeline Diagram

**Feature Branch**: `014-pipeline-diagram`

**Created**: 2026-10-01

**Status**: Draft

**Input**: Add a first-class architecture diagram representation from the Pipeline DSL.

## User Scenarios & Testing

### User Story 1 - Read Pipeline as a Diagram (Priority: P1)

An SDK user can ask a pipeline for a flow diagram text and understand source, inference, overlays, actions, and output.

## Requirements

- **FR-001**: Pipeline MUST expose `diagram()`.
- **FR-002**: Diagram MUST include source or stream declarations.
- **FR-003**: Diagram MUST show actions as branches from the main flow.
- **FR-004**: Diagram MUST remain deterministic for tests and docs.

## Success Criteria

- **SC-001**: Tests verify a single-stream diagram contains the main flow and action branches.
- **SC-002**: Tests verify a multi-stream batch diagram shows streams and batch inference.
