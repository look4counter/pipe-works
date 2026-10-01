"""Minimal LOOP engineering engine."""

from __future__ import annotations

from pipeworks.core.models import LoopDecision, Task, TaskStatus
from pipeworks.core.ports import EvidenceRecorder, TaskBacklog, VerificationHarness, WorkAgent


class LoopEngine:
    """Select, execute, verify, and record one unblocked task at a time."""

    def __init__(
        self,
        backlog: TaskBacklog,
        agent: WorkAgent,
        harness: VerificationHarness,
        recorder: EvidenceRecorder,
    ) -> None:
        self._backlog = backlog
        self._agent = agent
        self._harness = harness
        self._recorder = recorder

    def run_once(self) -> LoopDecision:
        tasks = self._backlog.list_tasks()
        completed = {task.id for task in tasks if task.status == TaskStatus.DONE}
        task = self._select_task(tasks, completed)
        if task is None:
            return LoopDecision(
                task_id=None,
                should_continue=False,
                reason="No unblocked ready task is available.",
            )

        task.status = TaskStatus.RUNNING
        implementation = self._agent.perform(task)
        gate_results = self._harness.verify(task)
        evidence = [implementation, *[item for gate in gate_results for item in gate.evidence]]
        gates_passed = all(gate.passed for gate in gate_results)
        task.status = TaskStatus.DONE if implementation.passed and gates_passed else TaskStatus.BLOCKED
        self._recorder.record(task, evidence)

        if task.status == TaskStatus.DONE:
            return LoopDecision(
                task_id=task.id,
                should_continue=True,
                reason="Task accepted by harness.",
                evidence=evidence,
            )
        return LoopDecision(
            task_id=task.id,
            should_continue=False,
            reason="Task blocked by failed implementation evidence or quality gate.",
            evidence=evidence,
        )

    @staticmethod
    def _select_task(tasks: list[Task], completed: set[str]) -> Task | None:
        candidates = [task for task in tasks if task.is_unblocked_by(completed)]
        if not candidates:
            return None
        return min(candidates, key=lambda task: task.priority)
