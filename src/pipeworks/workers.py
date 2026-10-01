"""Deterministic runtime workers hidden behind the public Pipeline DSL."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from pipeworks.components import ActionDispatcher
from pipeworks.config import RuntimeConfig
from pipeworks.models import Frame, PipelineContext
from pipeworks.plan import PipelineStep


class SourceWorker:
    """Turn a source component's frames into runtime contexts."""

    def run(self, source: object) -> list[Frame]:
        return source.frames()  # type: ignore[attr-defined]


class InferenceWorker:
    def run(
        self, contexts: list[PipelineContext], step: PipelineStep, config: RuntimeConfig
    ) -> list[PipelineContext]:
        settings = config.for_component(step.component)
        component = step.component
        for context in contexts:
            result = component.infer(context, settings)  # type: ignore[attr-defined]
            context.add_result(result)
        return contexts


class BatchInferenceWorker:
    def run(
        self, contexts: list[PipelineContext], step: PipelineStep, config: RuntimeConfig
    ) -> list[PipelineContext]:
        settings = config.for_component(step.component, fallback="BatchInference")
        results = step.component.infer_batch(contexts, settings)  # type: ignore[attr-defined]
        if len(results) != len(contexts):
            raise ValueError("batch inference must return one result per context")
        for context, result in zip(contexts, results, strict=True):
            context.add_result(result)
        return contexts


class ProcessWorker:
    def run(self, contexts: list[PipelineContext], step: PipelineStep) -> list[PipelineContext]:
        return [step.component.process(context) for context in contexts]  # type: ignore[attr-defined]


class OverlayWorker:
    def run(self, contexts: list[PipelineContext], step: PipelineStep) -> list[PipelineContext]:
        return [step.component.apply(context) for context in contexts]  # type: ignore[attr-defined]


class ActionWorker:
    def run(
        self,
        contexts: list[PipelineContext],
        step: PipelineStep,
        config: RuntimeConfig,
        dispatcher: ActionDispatcher,
    ) -> list[PipelineContext]:
        settings = config.for_component(step.component, fallback="Action")
        for context in contexts:
            dispatcher.submit(step.component, context, settings)  # type: ignore[arg-type]
        return contexts


class OutputWorker:
    def run(
        self,
        contexts: list[PipelineContext],
        step: PipelineStep,
        config: RuntimeConfig,
        on_output: Callable[[], None],
    ) -> list[PipelineContext]:
        settings = config.for_component(step.component)
        for context in contexts:
            step.component.write(context, settings)  # type: ignore[attr-defined]
            on_output()
        return contexts


@dataclass(frozen=True)
class WorkerRunResult:
    contexts: list[PipelineContext]
    largest_batch_size: int
    output_count: int


class WorkerRuntime:
    """Execute plan stages through explicit workers.

    The first runtime is deliberately synchronous and deterministic. Queue and
    process scheduling remain implementation details that can be added behind
    these worker contracts without changing the DSL.
    """

    def __init__(self) -> None:
        self.inference = InferenceWorker()
        self.batch_inference = BatchInferenceWorker()
        self.process = ProcessWorker()
        self.overlay = OverlayWorker()
        self.action = ActionWorker()
        self.output = OutputWorker()

    def run(
        self,
        steps: tuple[PipelineStep, ...],
        contexts: list[PipelineContext],
        config: RuntimeConfig,
        dispatcher: ActionDispatcher,
    ) -> WorkerRunResult:
        output_count = 0
        largest_batch_size = 0
        for step in steps:
            if step.kind == "inference":
                contexts = self.inference.run(contexts, step, config)
            elif step.kind == "batch_inference":
                largest_batch_size = max(largest_batch_size, len(contexts))
                contexts = self.batch_inference.run(contexts, step, config)
            elif step.kind == "process":
                contexts = self.process.run(contexts, step)
            elif step.kind == "overlay":
                contexts = self.overlay.run(contexts, step)
            elif step.kind == "action":
                contexts = self.action.run(contexts, step, config, dispatcher)
            elif step.kind == "output":
                contexts = self.output.run(
                    contexts,
                    step,
                    config,
                    on_output=lambda: None,
                )
                output_count += len(contexts)
            else:
                raise ValueError(f"unknown pipeline step {step.kind!r}")
        return WorkerRunResult(
            contexts=contexts,
            largest_batch_size=largest_batch_size,
            output_count=output_count,
        )
