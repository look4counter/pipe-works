"""Ports used by the loop engine.

Adapters implement these protocols for local tools, CI, issue trackers, model
providers, or external harnesses without leaking vendor details into core logic.
"""

from __future__ import annotations

from typing import Protocol

from pipeworks.core.models import Evidence, GateResult, Task


class TaskBacklog(Protocol):
    def list_tasks(self) -> list[Task]:
        """Return known tasks in priority order."""


class WorkAgent(Protocol):
    def perform(self, task: Task) -> Evidence:
        """Attempt one task and return implementation evidence."""


class VerificationHarness(Protocol):
    def verify(self, task: Task) -> list[GateResult]:
        """Run quality gates for a task."""


class EvidenceRecorder(Protocol):
    def record(self, task: Task, evidence: list[Evidence]) -> None:
        """Persist evidence for handoff, audit, and future loops."""
