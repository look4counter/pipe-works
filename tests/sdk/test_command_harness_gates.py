import sys

from pipeworks.core.models import AcceptanceCriterion, Task
from pipeworks.harness.gates import CommandGate


def test_command_gate_passes_when_command_exits_zero() -> None:
    task = Task(
        id="T-CMD-1",
        title="passing command",
        priority=1,
        acceptance=[AcceptanceCriterion("AC-1", "Command passes.")],
    )
    gate = CommandGate(
        name="pass-command",
        command=(sys.executable, "-c", "print('ok')"),
    )

    result = gate.run(task)

    assert result.passed is True
    assert "exit=0" in result.evidence[0].summary
    assert "ok" in result.evidence[0].summary


def test_command_gate_fails_when_command_exits_nonzero() -> None:
    task = Task(
        id="T-CMD-2",
        title="failing command",
        priority=1,
        acceptance=[AcceptanceCriterion("AC-1", "Command fails.")],
    )
    gate = CommandGate(
        name="fail-command",
        command=(sys.executable, "-c", "import sys; print('bad'); sys.exit(7)"),
    )

    result = gate.run(task)

    assert result.passed is False
    assert "exit=7" in result.evidence[0].summary
    assert "bad" in result.evidence[0].summary
