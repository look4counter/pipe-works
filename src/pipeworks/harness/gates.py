"""Composable quality gates for the SDK harness."""

from __future__ import annotations

import subprocess
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


@dataclass(frozen=True)
class CommandGate:
    """Quality gate backed by a local command."""

    name: str
    command: tuple[str, ...]
    timeout_s: float = 30.0
    cwd: str | None = None

    def run(self, task: Task) -> GateResult:
        try:
            completed = subprocess.run(
                self.command,
                cwd=self.cwd,
                capture_output=True,
                check=False,
                text=True,
                timeout=self.timeout_s,
            )
            output = (completed.stdout + completed.stderr).strip()
            summary = (
                f"command={' '.join(self.command)!r} exit={completed.returncode}"
                + (f" output={output[:500]}" if output else "")
            )
            evidence = Evidence(
                source=self.name,
                summary=summary,
                passed=completed.returncode == 0,
            )
            return GateResult(name=self.name, passed=evidence.passed, evidence=[evidence])
        except subprocess.TimeoutExpired as error:
            evidence = Evidence(
                source=self.name,
                summary=f"command={' '.join(self.command)!r} timed out after {error.timeout}s",
                passed=False,
            )
            return GateResult(name=self.name, passed=False, evidence=[evidence])


def ruff_gate(*paths: str, cwd: str | None = None) -> CommandGate:
    target_paths = paths or ("src/pipeworks", "tests/sdk")
    return CommandGate(name="ruff", command=("python", "-m", "ruff", "check", *target_paths), cwd=cwd)


def pytest_gate(*paths: str, cwd: str | None = None) -> CommandGate:
    target_paths = paths or ("tests/sdk",)
    return CommandGate(name="pytest", command=("python", "-m", "pytest", "-q", *target_paths), cwd=cwd)
