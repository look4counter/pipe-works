# Feature Specification: Pipeline DSL SDK

**Feature Branch**: `002-pipeline-dsl-sdk`

**Created**: 2026-10-01

**Status**: Draft

**Input**: User description: "Python real-time video processing Pipeline SDK whose Public API/DSL makes the video flow understandable within 10 seconds, with configuration separated into YAML, multi-stream and batch inference support, stream identity preservation, async actions, backpressure, custom components, multi-stage inference, and MVP-first implementation."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Declare a Readable Single-Stream Pipeline (Priority: P1)

An SDK user can declare a live video pipeline in fluent Python code that reads like the actual video flow: source, inference, overlays, actions, and output.

**Why this priority**: This is the central value of the SDK. If the Public API is not intuitive, the SDK fails even if internal runtime pieces work.

**Independent Test**: A developer can open a `pipeline.py` file and identify the input stream, model, overlays, external actions, and output target without reading runtime internals.

**Acceptance Scenarios**:

1. **Given** a pipeline with one source, one inference component, one overlay, one action, and one output, **When** the developer inspects the Python declaration, **Then** the video flow is understandable from the chained calls alone.
2. **Given** no external YAML file, **When** the user runs a pipeline with default-compatible components, **Then** the SDK applies safe defaults and executes the pipeline.

---

### User Story 2 - Configure How Without Hiding What (Priority: P1)

An SDK user can override runtime behavior such as timeout, retry, device, confidence, queue size, and drop policy through YAML without moving essential pipeline identity out of Python.

**Why this priority**: The SDK must keep Python DSL focused on "what is connected" while YAML controls "how it behaves".

**Independent Test**: A pipeline declaration still shows source URLs, model paths, action targets, and output URLs even when YAML overrides runtime behavior.

**Acceptance Scenarios**:

1. **Given** a YAML file that overrides component settings, **When** a matching component runs, **Then** only the behavior settings are overridden.
2. **Given** a Python pipeline declaration, **When** all YAML is removed, **Then** essential pipeline meaning remains visible in Python.

---

### User Story 3 - Preserve Stream Identity in Multi-Stream Pipelines (Priority: P2)

An SDK user can declare multiple streams and batch inference while the SDK preserves each frame and result's stream identity automatically.

**Why this priority**: Multi-camera batch inference is a primary use case and should not force users to write collector/demultiplexer code.

**Independent Test**: Running a mock 3-stream batch pipeline produces per-stream contexts and outputs mapped back to their original streams.

**Acceptance Scenarios**:

1. **Given** multiple streams, **When** frames are processed through batch inference, **Then** each result remains associated with its original `stream_id`.
2. **Given** one stream is delayed or absent, **When** the batch wait limit is reached, **Then** the SDK proceeds according to the configured real-time policy without unbounded backlog.

---

### User Story 4 - Extend the Pipeline with Custom Components (Priority: P2)

An SDK user can insert custom processing logic without modifying SDK internals.

**Why this priority**: Real projects need domain-specific filtering, transforms, actions, and overlays.

**Independent Test**: A custom component implementing the expected protocol can be inserted with `.process(...)` and can update context data.

**Acceptance Scenarios**:

1. **Given** a custom processor, **When** it is inserted between inference and overlay, **Then** downstream components receive the modified context.
2. **Given** a component raises an error, **When** the runtime handles the context, **Then** the failure is recorded without exposing thread, queue, or lock management to normal users.

---

### User Story 5 - Support Multi-Stage Inference (Priority: P3)

An SDK user can call a primary model, transform/crop results, call a secondary model, and overlay final results while each inference output remains available in context.

**Why this priority**: Cascaded AI models are common in real video analytics.

**Independent Test**: A mock pipeline with two inference stages records distinct result entries for each stage.

**Acceptance Scenarios**:

1. **Given** two inference stages, **When** the pipeline runs, **Then** the context stores stage-specific inference results.
2. **Given** a transform between inference stages, **When** the second model runs, **Then** it receives the transformed context rather than requiring user-managed intermediate buffers.

### Edge Cases

- A source emits no frames before timeout.
- A stream disconnects or is slower than other streams.
- Batch size is not reached before `max_wait_ms`.
- A slow action should not block video output.
- A component fails for one frame or stream.
- A custom component returns invalid data.
- YAML refers to an unknown component or setting.
- Multiple inference stages use the same model class.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The SDK MUST provide a fluent `Pipeline` DSL that exposes source, inference, transform/process, overlay, action, output, multi-stream, and batch inference concepts.
- **FR-002**: The Python DSL MUST keep essential "what" values visible, including source identity, model identity, action targets, and output targets.
- **FR-003**: Runtime "how" settings MUST be configurable through optional YAML overrides while retaining safe defaults.
- **FR-004**: The SDK MUST run without YAML by applying default configuration.
- **FR-005**: The SDK MUST provide stream-aware `Frame`, `PipelineContext`, and result models with `stream_id`, timestamp, sequence, and stage identity.
- **FR-006**: Multi-stream execution MUST preserve frame/result mapping after batch inference.
- **FR-007**: Batch inference MUST be represented in the Public API, not hidden only as a tuning parameter.
- **FR-008**: Actions MUST be modeled as non-blocking side effects relative to the main video path.
- **FR-009**: Runtime internals such as queues, locks, reconnect loops, CUDA contexts, batch collectors, demultiplexers, and encoders MUST be hidden from normal Public API users.
- **FR-010**: The SDK MUST allow custom components through protocols or composition without requiring SDK source changes.
- **FR-011**: Multi-stage inference MUST keep stage-specific results available to downstream components.
- **FR-012**: MVP execution MUST be testable without cameras, GPUs, message queues, or RTSP servers.
- **FR-013**: The SDK MUST provide readable examples for single-stream, multi-stream batch, multi-stage inference, and custom components.
- **FR-014**: Key architecture decisions MUST be recorded as ADRs with rationale and trade-offs.
- **FR-015**: Test coverage MUST verify DSL readability contracts, configuration override behavior, stream identity preservation, async action behavior, custom extension, and multi-stage inference.

### Key Entities *(include if feature involves data)*

- **Pipeline**: User-facing declaration of video flow and runtime entry point.
- **Stream**: Named input/output pair for multi-stream processing.
- **Frame**: Stream-aware frame payload with timestamp and sequence.
- **PipelineContext**: Per-frame processing context that carries frame, detections, stage results, overlays, action events, errors, and metadata.
- **DetectionResult**: Inference output associated with stream and stage.
- **Component**: Source, inference, transform, overlay, action, or output inserted into a pipeline.
- **RuntimeConfig**: Defaults plus YAML overrides for behavior settings.
- **PipelineResult**: Execution summary including contexts, metrics, and errors.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A new developer can identify input, model, actions, and output from a representative `pipeline.py` in under 10 seconds.
- **SC-002**: Single-stream MVP pipelines run in local tests without external services.
- **SC-003**: Multi-stream batch tests prove that every output context has the same `stream_id` as its originating frame.
- **SC-004**: A slow action does not increase synchronous pipeline run time by more than 100 ms in MVP tests.
- **SC-005**: YAML overrides change behavior settings without removing source/model/action/output identity from Python examples.
- **SC-006**: At least four examples demonstrate single-stream, multi-stream batch, multi-stage inference, and custom components.

## Assumptions

- MVP uses in-memory/mock components for deterministic tests.
- Real RTSP, GStreamer, TensorRT, CUDA, MQ, and MediaMTX adapters are later slices.
- Python 3.11.9 remains the target runtime from project configuration.
- The initial runtime can be synchronous for the main path while actions use background workers to prove non-blocking behavior.
- Batch inference in MVP groups currently available frames and applies timeout/drop policy semantics without GPU execution.
