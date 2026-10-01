"""Deterministic runtime workers hidden behind the public Pipeline DSL."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from time import sleep

from pipeworks.components import ActionDispatcher
from pipeworks.config import RuntimeConfig
from pipeworks.models import Frame, PipelineContext
from pipeworks.plan import PipelineStep


class SourceWorker:
    """Turn a source component's frames into runtime contexts."""

    def run(self, source: object, config: RuntimeConfig | None = None) -> list[Frame]:
        settings = config.for_component(source) if config is not None else {}
        reconnect = bool(settings.get("reconnect", False))
        attempts = int(settings.get("reconnect_attempts", 1)) if reconnect else 1
        interval = float(settings.get("reconnect_interval", 0))
        last_error: Exception | None = None
        for attempt in range(max(attempts, 1)):
            try:
                return source.frames()  # type: ignore[attr-defined]
            except Exception as error:  # noqa: BLE001
                last_error = error
                if attempt + 1 < attempts and interval > 0:
                    sleep(interval)
        if last_error is not None:
            raise last_error
        return []


class InferenceWorker:
    def __init__(self, isolate_errors: bool = False) -> None:
        self.isolate_errors = isolate_errors

    def run(
        self, contexts: list[PipelineContext], step: PipelineStep, config: RuntimeConfig
    ) -> list[PipelineContext]:
        settings = config.for_component(step.component)
        component = step.component
        for context in contexts:
            try:
                result = component.infer(context, settings)  # type: ignore[attr-defined]
                context.add_result(result)
            except Exception as error:
                if not self.isolate_errors:
                    raise
                context.errors.append(f"inference failed: {error}")
        return contexts


class BatchInferenceWorker:
    def __init__(self, isolate_errors: bool = False) -> None:
        self.isolate_errors = isolate_errors

    def run(
        self, contexts: list[PipelineContext], step: PipelineStep, config: RuntimeConfig
    ) -> list[PipelineContext]:
        settings = config.for_component(step.component, fallback="BatchInference")
        try:
            results = step.component.infer_batch(contexts, settings)  # type: ignore[attr-defined]
        except Exception as error:
            if not self.isolate_errors:
                raise
            for context in contexts:
                context.errors.append(f"batch inference failed: {error}")
            return contexts
        if len(results) != len(contexts):
            error = "batch inference must return one result per context"
            for context in contexts:
                context.errors.append(error)
            return contexts
        for context, result in zip(contexts, results, strict=True):
            try:
                context.add_result(result)
            except Exception as error:
                if not self.isolate_errors:
                    raise
                context.errors.append(f"batch result failed: {error}")
        return contexts


class ProcessWorker:
    def __init__(self, isolate_errors: bool = False) -> None:
        self.isolate_errors = isolate_errors

    def run(self, contexts: list[PipelineContext], step: PipelineStep) -> list[PipelineContext]:
        for index, context in enumerate(contexts):
            try:
                contexts[index] = step.component.process(context)  # type: ignore[attr-defined]
            except Exception as error:
                if not self.isolate_errors:
                    raise
                context.errors.append(f"process failed: {error}")
        return contexts


class OverlayWorker:
    def __init__(self, isolate_errors: bool = False) -> None:
        self.isolate_errors = isolate_errors

    def run(self, contexts: list[PipelineContext], step: PipelineStep) -> list[PipelineContext]:
        for index, context in enumerate(contexts):
            try:
                contexts[index] = step.component.apply(context)  # type: ignore[attr-defined]
            except Exception as error:
                if not self.isolate_errors:
                    raise
                context.errors.append(f"overlay failed: {error}")
        return contexts


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
    def __init__(self, isolate_errors: bool = False) -> None:
        self.isolate_errors = isolate_errors

    def run(
        self,
        contexts: list[PipelineContext],
        step: PipelineStep,
        config: RuntimeConfig,
        on_output: Callable[[], None],
    ) -> list[PipelineContext]:
        settings = config.for_component(step.component)
        for context in contexts:
            try:
                step.component.write(context, settings)  # type: ignore[attr-defined]
                on_output()
            except Exception as error:
                if not self.isolate_errors:
                    raise
                context.errors.append(f"output failed: {error}")
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

    def __init__(self, isolate_errors: bool = False) -> None:
        self.inference = InferenceWorker(isolate_errors)
        self.batch_inference = BatchInferenceWorker(isolate_errors)
        self.process = ProcessWorker(isolate_errors)
        self.overlay = OverlayWorker(isolate_errors)
        self.action = ActionWorker()
        self.output = OutputWorker(isolate_errors)

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
                successful_outputs = 0

                def count_output() -> None:
                    nonlocal successful_outputs
                    successful_outputs += 1

                contexts = self.output.run(
                    contexts,
                    step,
                    config,
                    on_output=count_output,
                )
                output_count += successful_outputs
            else:
                raise ValueError(f"unknown pipeline step {step.kind!r}")
        return WorkerRunResult(
            contexts=contexts,
            largest_batch_size=largest_batch_size,
            output_count=output_count,
        )
