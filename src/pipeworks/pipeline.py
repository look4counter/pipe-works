"""Fluent Pipeline DSL and deterministic MVP runtime."""

from __future__ import annotations

from pathlib import Path
from time import perf_counter

from pipeworks.components import (
    ActionComponent,
    ActionDispatcher,
    BatchInferenceComponent,
    InferenceComponent,
    OutputComponent,
    OverlayComponent,
    ProcessorComponent,
    SourceComponent,
)
from pipeworks.config import RuntimeConfig
from pipeworks.lifecycle import Lifecycle, PipelineState
from pipeworks.models import Frame, PipelineContext, PipelineMetrics, PipelineResult, Stream
from pipeworks.plan import PipelinePlan, PipelineStep
from pipeworks.runtime import BatchCollector, BatchPolicy, DropPolicy, FrameQueue, QueueMetrics


class Pipeline:
    """Readable video pipeline declaration.

    The chained calls are intentionally the product API. Runtime internals are
    compiled from this declaration during `run()`.
    """

    def __init__(self, name: str = "pipeline", config: str | Path | RuntimeConfig | None = None) -> None:
        self.name = name
        self._source: SourceComponent | None = None
        self._streams: list[Stream] = []
        self._steps: list[PipelineStep] = []
        self._last_queue_metrics: list[QueueMetrics] = []
        self._lifecycle = Lifecycle()
        if isinstance(config, RuntimeConfig):
            self._config = config
        else:
            self._config = RuntimeConfig.from_yaml(config)

    def source(self, component: SourceComponent) -> Pipeline:
        self._source = component
        return self

    def streams(self, streams: list[Stream]) -> Pipeline:
        self._streams = streams
        return self

    def inference(self, component: InferenceComponent) -> Pipeline:
        self._steps.append(PipelineStep("inference", component))
        return self

    def batch_inference(self, component: BatchInferenceComponent) -> Pipeline:
        self._steps.append(PipelineStep("batch_inference", component))
        return self

    def transform(self, component: ProcessorComponent) -> Pipeline:
        self._steps.append(PipelineStep("process", component))
        return self

    def process(self, component: ProcessorComponent) -> Pipeline:
        self._steps.append(PipelineStep("process", component))
        return self

    def overlay(self, component: OverlayComponent) -> Pipeline:
        self._steps.append(PipelineStep("overlay", component))
        return self

    def action(self, component: ActionComponent) -> Pipeline:
        self._steps.append(PipelineStep("action", component))
        return self

    def output(self, component: OutputComponent) -> Pipeline:
        self._steps.append(PipelineStep("output", component))
        return self

    def compile(self) -> PipelinePlan:
        """Compile the fluent declaration into a read-only execution plan."""

        return PipelinePlan(
            name=self.name,
            source=self._source,
            streams=tuple(self._streams),
            steps=tuple(self._steps),
            config=self._config,
        )

    def describe(self) -> list[str]:
        """Return a simple architecture-diagram-like summary."""

        return self.compile().describe()

    def diagram(self) -> str:
        """Return a readable text diagram for the declared pipeline."""

        lines: list[str] = [f"Pipeline: {self.name}"]
        plan = self.compile()
        if plan.streams:
            lines.extend(f"{stream.stream_id}: {stream.source}" for stream in plan.streams)
        elif plan.source is not None:
            lines.append(PipelinePlan.describe_component(plan.source))
        else:
            lines.append("<no source>")

        main_steps = [step for step in plan.steps if step.kind != "action"]
        action_steps = [step for step in plan.steps if step.kind == "action"]
        for step in main_steps:
            lines.append("  |")
            label = "batch inference" if step.kind == "batch_inference" else step.kind
            lines.append(f"{label}: {PipelinePlan.describe_component(step.component)}")
            if action_steps and step.kind in {"overlay", "batch_inference", "inference"}:
                for action in action_steps:
                    lines.append(f"  +-- action: {PipelinePlan.describe_component(action.component)}")
                action_steps = []
        for action in action_steps:
            lines.append(f"  +-- action: {PipelinePlan.describe_component(action.component)}")
        return "\n".join(lines)

    def run(self, wait_for_actions: bool = True) -> PipelineResult:
        run_started_at = perf_counter()
        self._lifecycle.transition(PipelineState.STARTING)
        dispatcher = ActionDispatcher()
        try:
            contexts = self._initial_contexts()
            queue_metrics = self._last_queue_metrics
            output_count = 0
            largest_batch_size = 0
            self._lifecycle.transition(PipelineState.RUNNING)

            for step in self._steps:
                if step.kind == "inference":
                    component = step.component
                    settings = self._config.for_component(component)
                    for context in contexts:
                        result = component.infer(context, settings)  # type: ignore[attr-defined]
                        context.add_result(result)
                elif step.kind == "batch_inference":
                    component = step.component
                    settings = self._config.for_component(component, fallback="BatchInference")
                    largest_batch_size = max(largest_batch_size, len(contexts))
                    results = component.infer_batch(contexts, settings)  # type: ignore[attr-defined]
                    if len(results) != len(contexts):
                        raise ValueError("batch inference must return one result per context")
                    for context, result in zip(contexts, results, strict=True):
                        context.add_result(result)
                elif step.kind == "process":
                    contexts = [
                        step.component.process(context) for context in contexts  # type: ignore[attr-defined]
                    ]
                elif step.kind == "overlay":
                    contexts = [
                        step.component.apply(context) for context in contexts  # type: ignore[attr-defined]
                    ]
                elif step.kind == "action":
                    component = step.component
                    settings = self._config.for_component(component, fallback="Action")
                    for context in contexts:
                        dispatcher.submit(component, context, settings)  # type: ignore[arg-type]
                elif step.kind == "output":
                    component = step.component
                    settings = self._config.for_component(component)
                    for context in contexts:
                        component.write(context, settings)  # type: ignore[attr-defined]
                        output_count += 1
                else:
                    raise ValueError(f"unknown pipeline step {step.kind!r}")

            self._lifecycle.transition(PipelineState.DRAINING)
            dispatcher.drain(wait_for_actions=wait_for_actions)
            self._lifecycle.transition(PipelineState.STOPPED)
            duration_ms = (perf_counter() - run_started_at) * 1000
            error_count = dispatcher.errors + sum(len(context.errors) for context in contexts)
            action_latency_avg = (
                sum(dispatcher.latency_ms) / len(dispatcher.latency_ms)
                if dispatcher.latency_ms
                else 0.0
            )
            return PipelineResult(
                pipeline_name=self.name,
                contexts=contexts,
                state=self.state.value,
                metrics=PipelineMetrics(
                    frames_processed=len(contexts),
                    actions_scheduled=dispatcher.scheduled,
                    actions_completed=dispatcher.completed,
                    action_errors=dispatcher.errors,
                    output_count=output_count,
                    error_count=error_count,
                    queue_dropped=sum(metrics.dropped_count for metrics in queue_metrics),
                    queue_max_depth=max((metrics.max_depth_seen for metrics in queue_metrics), default=0),
                    batch_size=largest_batch_size,
                    duration_ms=duration_ms,
                    effective_fps=(len(contexts) / (duration_ms / 1000)) if duration_ms > 0 else 0.0,
                    action_latency_ms_max=max(dispatcher.latency_ms, default=0.0),
                    action_latency_ms_avg=action_latency_avg,
                ),
            )
        except Exception:
            dispatcher.drain(wait_for_actions=False)
            self._lifecycle.transition(PipelineState.ERROR)
            raise

    @property
    def state(self) -> PipelineState:
        return self._lifecycle.state

    def _initial_contexts(self) -> list[PipelineContext]:
        if self._streams:
            return self._initial_stream_contexts()
        if self._source is None:
            raise ValueError("pipeline requires either source(...) or streams(...)")
        return self._contexts_from_frames(self._source.frames())

    def _initial_stream_contexts(self) -> list[PipelineContext]:
        queue_settings = self._config.sections.get("Pipeline", {})
        batch_settings = self._config.sections.get("BatchInference", {})
        stream_queues = {
            stream.stream_id: FrameQueue(
                max_frames=int(queue_settings.get("queue_size", 8)),
                drop_policy=str(queue_settings.get("drop_policy", DropPolicy.LATEST.value)),
            )
            for stream in self._streams
        }
        for stream in self._streams:
            stream_queues[stream.stream_id].put(
                Frame(
                    stream_id=stream.stream_id,
                    image=stream.source,
                    sequence=0,
                    metadata={"source": stream.source, "output": stream.output},
                )
            )
        self._last_queue_metrics = [queue.metrics for queue in stream_queues.values()]
        if any(step.kind == "batch_inference" for step in self._steps):
            return BatchCollector(
                stream_queues,
                BatchPolicy(
                    max_batch_size=int(batch_settings.get("max_batch_size", len(stream_queues))),
                    max_wait_ms=int(batch_settings.get("max_wait_ms", 20)),
                    drop_policy=str(batch_settings.get("drop_policy", DropPolicy.LATEST.value)),
                ),
            ).collect()
        return [
            PipelineContext(frame=frame)
            for queue in stream_queues.values()
            for frame in queue.drain_all()
        ]

    def _contexts_from_frames(self, frames: list[Frame]) -> list[PipelineContext]:
        queue_settings = self._config.sections.get("Pipeline", {})
        queues: dict[str, FrameQueue] = {}
        for frame in frames:
            queue = queues.setdefault(
                frame.stream_id,
                FrameQueue(
                    max_frames=int(queue_settings.get("queue_size", 8)),
                    drop_policy=str(queue_settings.get("drop_policy", DropPolicy.LATEST.value)),
                ),
            )
            queue.put(frame)
        self._last_queue_metrics = [queue.metrics for queue in queues.values()]
        return [
            PipelineContext(frame=frame)
            for queue in queues.values()
            for frame in queue.drain_all()
        ]
