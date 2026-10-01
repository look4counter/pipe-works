"""In-memory adapters for tests and early SDK examples."""

from __future__ import annotations

from dataclasses import dataclass, field

from pipeworks.core.models import Evidence, Task


@dataclass
class InMemoryBacklog:
    tasks: list[Task]

    def list_tasks(self) -> list[Task]:
        return sorted(self.tasks, key=lambda task: task.priority)


class NoOpAgent:
    def perform(self, task: Task) -> Evidence:
        return Evidence(
            source="noop-agent",
            summary=f"Prepared task {task.id}: {task.title}",
            passed=True,
        )


@dataclass
class InMemoryRecorder:
    records: dict[str, list[Evidence]] = field(default_factory=dict)

    def record(self, task: Task, evidence: list[Evidence]) -> None:
        self.records[task.id] = evidence
