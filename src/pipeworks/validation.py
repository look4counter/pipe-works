"""Early validation for declared pipeline plans."""

from __future__ import annotations

from dataclasses import dataclass

from pipeworks.plan import PipelinePlan


class PipelineValidationError(ValueError):
    """Raised when a pipeline cannot be executed unambiguously."""


@dataclass(frozen=True)
class ValidationReport:
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def valid(self) -> bool:
        return not self.errors

    def raise_for_errors(self) -> None:
        if self.errors:
            raise PipelineValidationError("; ".join(self.errors))


def validate_plan(plan: PipelinePlan) -> ValidationReport:
    errors: list[str] = []
    warnings: list[str] = []

    if plan.source is None and not plan.streams:
        errors.append("pipeline requires either source(...) or streams(...)")
    if plan.source is not None and plan.streams:
        errors.append("pipeline cannot declare both source(...) and streams(...)")

    stream_ids = [stream.stream_id for stream in plan.streams]
    duplicates = sorted({stream_id for stream_id in stream_ids if stream_ids.count(stream_id) > 1})
    if duplicates:
        errors.append(f"stream IDs must be unique: {', '.join(duplicates)}")

    if plan.has_batch_inference and plan.source is None and not plan.streams:
        errors.append("batch_inference(...) requires a source or streams")

    if not any(step.kind == "output" for step in plan.steps):
        warnings.append("pipeline has no output(...); results will remain in memory")

    if any(step.kind == "output" for step in plan.steps) and not any(
        step.kind in {"inference", "batch_inference", "process", "overlay"} for step in plan.steps
    ):
        warnings.append("pipeline publishes frames without a processing stage")

    return ValidationReport(errors=tuple(errors), warnings=tuple(warnings))
