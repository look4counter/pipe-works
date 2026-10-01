# Feature Specification: Inference Adapter Boundary

**Feature Branch**: `009-inference-adapter-boundary`

**Created**: 2026-10-01

**Status**: Draft

**Input**: Add lazy real inference adapter boundaries for YOLO/TensorRT without making heavyweight dependencies mandatory for SDK tests.

## User Scenarios & Testing

### User Story 1 - Use Real Inference Adapters When Installed (Priority: P1)

An SDK user can select a real inference adapter while local SDK tests still run without model runtimes.

**Acceptance Scenarios**:

1. **Given** runtime dependencies are unavailable, **When** adapter availability is checked, **Then** the SDK reports unavailable.
2. **Given** dependencies are unavailable, **When** inference is attempted, **Then** the SDK raises an actionable error.

## Requirements

- **FR-001**: Adapter imports MUST NOT require Ultralytics, TensorRT, or CUDA at import time.
- **FR-002**: Adapters MUST expose availability status.
- **FR-003**: Adapters MUST preserve stream identity and stage semantics.
- **FR-004**: Missing dependency errors MUST be actionable.

## Success Criteria

- **SC-001**: Tests pass without model runtime dependencies.
- **SC-002**: Adapter descriptors preserve model identity.
