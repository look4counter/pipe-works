from pipeworks.adapters.memory import InMemoryBacklog, InMemoryRecorder, NoOpAgent
from pipeworks.core.models import AcceptanceCriterion, Task, TaskStatus
from pipeworks.harness.gates import CompositeHarness, QualityGate, acceptance_gate
from pipeworks.loop.engine import LoopEngine


def test_loop_engine_completes_unblocked_task_and_records_evidence() -> None:
    task = Task(
        id="T-001",
        title="Prove loop harness",
        priority=1,
        acceptance=[AcceptanceCriterion(id="AC-001", statement="Evidence is recorded.")],
    )
    recorder = InMemoryRecorder()
    engine = LoopEngine(
        backlog=InMemoryBacklog([task]),
        agent=NoOpAgent(),
        harness=CompositeHarness([QualityGate("acceptance", acceptance_gate)]),
        recorder=recorder,
    )

    decision = engine.run_once()

    assert decision.task_id == "T-001"
    assert decision.should_continue is True
    assert task.status == TaskStatus.DONE
    assert len(recorder.records["T-001"]) == 2


def test_loop_engine_stops_when_dependencies_are_missing() -> None:
    task = Task(
        id="T-002",
        title="Blocked task",
        priority=1,
        acceptance=[AcceptanceCriterion(id="AC-002", statement="Dependency complete.")],
        depends_on={"T-001"},
    )
    engine = LoopEngine(
        backlog=InMemoryBacklog([task]),
        agent=NoOpAgent(),
        harness=CompositeHarness([QualityGate("acceptance", acceptance_gate)]),
        recorder=InMemoryRecorder(),
    )

    decision = engine.run_once()

    assert decision.task_id is None
    assert decision.should_continue is False
    assert task.status == TaskStatus.READY
