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
        dispatcher = ActionDispatcher()
        output_count = 0

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
            ),
        )

    def _initial_contexts(self) -> list[PipelineContext]:
        if self._streams:
            return [
                PipelineContext(
                    frame=Frame(
                        stream_id=stream.stream_id,
                        image=stream.source,
                        sequence=0,
                        metadata={"source": stream.source, "output": stream.output},
                    )
                )
                for stream in self._streams
            ]
        if self._source is None:
            raise ValueError("pipeline requires either source(...) or streams(...)")
        return [PipelineContext(frame=frame) for frame in self._source.frames()]

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
