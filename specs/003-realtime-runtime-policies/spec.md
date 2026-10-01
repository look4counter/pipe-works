# Feature Specification: Realtime Runtime Policies

**Feature Branch**: `003-realtime-runtime-policies`

**Created**: 2026-10-01

**Status**: Draft

**Input**: Continue autonomously after Pipeline DSL MVP by implementing the next SDK layer for real-time backpressure, frame drop, and batch collection policies.

## User Scenarios & Testing

### User Story 1 - Keep Real-Time Freshness Under Backlog (Priority: P1)

An SDK user can rely on bounded queues so a slow stage does not accumulate unbounded old frames.

**Why this priority**: Real-time video pipelines should prefer fresh frames over stale backlog.

**Independent Test**: A queue with capacity 2 and `drop_oldest` keeps the newest frames and records drops.

**Acceptance Scenarios**:

1. **Given** a full queue, **When** a new frame arrives with `drop_oldest`, **Then** the oldest frame is removed and drop metrics increase.
2. **Given** a full queue, **When** a new frame arrives with `drop_newest`, **Then** the incoming frame is rejected and drop metrics increase.

---

### User Story 2 - Build Batches Without User Demux Code (Priority: P1)

An SDK user can declare batch inference while the runtime collects one frame per stream and preserves stream identity.

**Why this priority**: Multi-camera batch inference is a key use case and must not require user-owned collector/demux logic.

**Independent Test**: A batch collector receives frames from several streams and returns contexts ordered by stream identity while preserving source metadata.

**Acceptance Scenarios**:

1. **Given** frames from multiple streams, **When** the collector builds a batch, **Then** the batch contains at most one latest frame per stream.
2. **Given** more streams than `max_batch_size`, **When** a batch is built, **Then** it is capped by policy.

### Edge Cases

- Empty queues.
- Duplicate frames from the same stream.
- Batch size smaller than stream count.
- Full queue with `block` policy.
- Invalid queue capacity.

## Requirements

### Functional Requirements

- **FR-001**: Runtime MUST provide a bounded frame queue.
- **FR-002**: Queue policies MUST include `drop_oldest`, `drop_newest`, and `block`.
- **FR-003**: Queue metrics MUST include depth, dropped count, and max depth seen.
- **FR-004**: Runtime MUST provide a batch collector that preserves `stream_id`.
- **FR-005**: Batch collector MUST select latest frames per stream by default.
- **FR-006**: Batch collector MUST cap output by `max_batch_size`.
- **FR-007**: These policies MUST remain internal/runtime-level and not pollute the normal Pipeline DSL.

### Key Entities

- **FrameQueue**: Bounded queue for real-time frame buffering.
- **QueueMetrics**: Depth and drop counters.
- **BatchPolicy**: Batch size, wait, and stream selection policy.
- **BatchCollector**: Runtime helper that turns stream queues into contexts.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Queue tests prove bounded memory behavior for every supported drop policy.
- **SC-002**: Batch collector tests prove stream identity preservation.
- **SC-003**: Existing Pipeline DSL tests continue to pass unchanged.

## Assumptions

- MVP batch collection is deterministic and synchronous.
- Future RTSP/GPU runtime can reuse these policy objects behind worker queues.
