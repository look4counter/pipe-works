"""Domain-neutral models for agentic engineering loops."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from time import time


class TaskStatus(str, Enum):
    """Lifecycle state for a task selected by the agent loop."""

    READY = "ready"
    RUNNING = "running"
    BLOCKED = "blocked"
    DONE = "done"


@dataclass(frozen=True)
class AcceptanceCriterion:
    """A measurable condition that proves a task is complete."""

    id: str
    statement: str


@dataclass
class Task:
    """Smallest useful vertical slice an agent can attempt."""

    id: str
    title: str
    priority: int
    acceptance: list[AcceptanceCriterion]
    status: TaskStatus = TaskStatus.READY
    depends_on: set[str] = field(default_factory=set)

    def is_unblocked_by(self, completed_task_ids: set[str]) -> bool:
        return self.status == TaskStatus.READY and self.depends_on.issubset(completed_task_ids)


@dataclass(frozen=True)
class Evidence:
    """A durable record produced by a harness or reviewer."""

    source: str
    summary: str
    passed: bool
    timestamp: float = field(default_factory=time)


@dataclass(frozen=True)
class GateResult:
    """Result for one quality gate."""

    name: str
    passed: bool
    evidence: list[Evidence]


@dataclass(frozen=True)
class LoopDecision:
    """Decision returned after one agent loop turn."""

    task_id: str | None
    should_continue: bool
    reason: str
    evidence: list[Evidence] = field(default_factory=list)
