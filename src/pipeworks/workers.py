"""Deterministic runtime workers hidden behind the public Pipeline DSL."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from time import perf_counter, sleep

from pipeworks.components import ActionDispatcher
from pipeworks.config import RuntimeConfig
from pipeworks.models import Frame, PipelineContext
from pipeworks.plan import PipelineStep
from pipeworks.runtime import ContextQueue


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

    def stream(self, source: object, config: RuntimeConfig | None = None):
        """Return a lazy frame iterator for continuous sources."""

        if hasattr(source, "stream_frames"):
            return source.stream_frames()  # type: ignore[attr-defined]
        return iter(self.run(source, config))


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
    queue_dropped: int = 0
    queue_max_depth: int = 0
    batch_count: int = 0
    batch_items: int = 0
    inference_latency_ms: float = 0.0


class ContinuousPipelineRunner:
    """Consume one frame per source per cycle and preserve stream identity."""

    def run(
        self,
        sources: dict[str, object],
        steps: tuple[PipelineStep, ...],
        config: RuntimeConfig,
        dispatcher: ActionDispatcher,
        max_cycles: int | None = None,
        isolate_errors: bool = False,
    ) -> WorkerRunResult:
        iterators = {
            stream_id: iter(SourceWorker().stream(source, config))
            for stream_id, source in sorted(sources.items())
        }
        contexts: list[PipelineContext] = []
        output_count = 0
        largest_batch_size = 0
        queue_dropped = 0
        queue_max_depth = 0
        batch_count = 0
        batch_items = 0
        inference_latency_ms = 0.0
        runtime = WorkerRuntime(isolate_errors=isolate_errors)
        cycle = 0
        while iterators and (max_cycles is None or cycle < max_cycles):
            current: list[PipelineContext] = []
            exhausted: list[str] = []
            for stream_id, iterator in iterators.items():
                try:
                    frame = next(iterator)
                except StopIteration:
                    exhausted.append(stream_id)
                    continue
                if frame.stream_id != stream_id:
                    raise ValueError(
                        f"source {stream_id!r} yielded frame for {frame.stream_id!r}"
                    )
                current.append(PipelineContext(frame=frame))
            for stream_id in exhausted:
                del iterators[stream_id]
            if not current:
                break
            result = runtime.run(steps, current, config, dispatcher)
            contexts.extend(result.contexts)
            output_count += result.output_count
            largest_batch_size = max(largest_batch_size, result.largest_batch_size)
            queue_dropped += result.queue_dropped
            queue_max_depth = max(queue_max_depth, result.queue_max_depth)
            batch_count += result.batch_count
            batch_items += result.batch_items
            inference_latency_ms += result.inference_latency_ms
            cycle += 1
        return WorkerRunResult(
            contexts=contexts,
            largest_batch_size=largest_batch_size,
            output_count=output_count,
            queue_dropped=queue_dropped,
            queue_max_depth=queue_max_depth,
            batch_count=batch_count,
            batch_items=batch_items,
            inference_latency_ms=inference_latency_ms,
        )


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
        queue_dropped = 0
        queue_max_depth = 0
        batch_count = 0
        batch_items = 0
        inference_latency_ms = 0.0
        queue_settings = config.sections.get("Pipeline", {})
        queue_size = int(queue_settings.get("worker_queue_size", 64))
        drop_policy = str(queue_settings.get("worker_drop_policy", "latest"))

        def handoff(values: list[PipelineContext]) -> list[PipelineContext]:
            nonlocal queue_dropped, queue_max_depth
            queue = ContextQueue(queue_size, drop_policy)
            for value in values:
                queue.put(value)
            queue_metrics = queue.metrics
            queue_dropped += queue_metrics.dropped_count
            queue_max_depth = max(queue_max_depth, queue_metrics.max_depth_seen)
            return queue.drain_all()

        for step in steps:
            if step.kind == "inference":
                started_at = perf_counter()
                contexts = self.inference.run(contexts, step, config)
                inference_latency_ms += (perf_counter() - started_at) * 1000
            elif step.kind == "batch_inference":
                largest_batch_size = max(largest_batch_size, len(contexts))
                batch_count += 1
                batch_items += len(contexts)
                started_at = perf_counter()
                contexts = self.batch_inference.run(contexts, step, config)
                inference_latency_ms += (perf_counter() - started_at) * 1000
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
            if step.kind != "output":
                contexts = handoff(contexts)
        return WorkerRunResult(
            contexts=contexts,
            largest_batch_size=largest_batch_size,
            output_count=output_count,
            queue_dropped=queue_dropped,
            queue_max_depth=queue_max_depth,
            batch_count=batch_count,
            batch_items=batch_items,
            inference_latency_ms=inference_latency_ms,
        )
