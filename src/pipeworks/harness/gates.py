"""Composable quality gates for the SDK harness."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from pipeworks.core.models import Evidence, GateResult, Task


GateCheck = Callable[[Task], Evidence]


@dataclass(frozen=True)
class QualityGate:
    name: str
    check: GateCheck

    def run(self, task: Task) -> GateResult:
        evidence = self.check(task)
        return GateResult(name=self.name, passed=evidence.passed, evidence=[evidence])


class CompositeHarness:
    """Run a fixed set of gates for a task."""

    def __init__(self, gates: list[QualityGate]) -> None:
        self._gates = gates

    def verify(self, task: Task) -> list[GateResult]:
        return [gate.run(task) for gate in self._gates]


def acceptance_gate(task: Task) -> Evidence:
    missing = [item.id for item in task.acceptance if not item.statement.strip()]
    passed = not missing
    summary = "All acceptance criteria are explicit." if passed else f"Missing: {missing}"
    return Evidence(source="acceptance-gate", summary=summary, passed=passed)
