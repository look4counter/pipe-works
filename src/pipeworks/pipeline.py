"""Fluent Pipeline DSL and deterministic MVP runtime."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
from pipeworks.models import Frame, PipelineContext, PipelineMetrics, PipelineResult, Stream
from pipeworks.runtime import BatchCollector, BatchPolicy, DropPolicy, FrameQueue, QueueMetrics


@dataclass(frozen=True)
class PipelineStep:
    kind: str
    component: object


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

    def describe(self) -> list[str]:
        """Return a simple architecture-diagram-like summary."""

        lines = [f"Pipeline({self.name})"]
        if self._source is not None:
            lines.append(f"source: {self._describe_component(self._source)}")
        if self._streams:
            lines.append(f"streams: {', '.join(stream.stream_id for stream in self._streams)}")
        for step in self._steps:
            lines.append(f"{step.kind}: {self._describe_component(step.component)}")
        return lines

    def run(self, wait_for_actions: bool = True) -> PipelineResult:
        contexts = self._initial_contexts()
        queue_metrics = self._last_queue_metrics
        dispatcher = ActionDispatcher()
        output_count = 0
        largest_batch_size = 0

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
                contexts = [step.component.process(context) for context in contexts]  # type: ignore[attr-defined]
            elif step.kind == "overlay":
                contexts = [step.component.apply(context) for context in contexts]  # type: ignore[attr-defined]
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

        # Output path is not blocked by actions. By default we drain before
        # returning a deterministic summary; advanced callers can opt out.
        dispatcher.drain(wait_for_actions=wait_for_actions)
        error_count = dispatcher.errors + sum(len(context.errors) for context in contexts)
        return PipelineResult(
            pipeline_name=self.name,
            contexts=contexts,
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
            ),
        )

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

    @staticmethod
    def _describe_component(component: Any) -> str:
        values: list[str] = []
        for attr in ("url", "model", "topic", "stream_id"):
            if hasattr(component, attr):
                value = getattr(component, attr)
                if value:
                    values.append(f"{attr}={value}")
        suffix = f"({', '.join(values)})" if values else ""
        return f"{component.__class__.__name__}{suffix}"
