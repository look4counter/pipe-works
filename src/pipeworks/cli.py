"""Command line entry point for the Pipe Works loop harness."""

from __future__ import annotations

import argparse

from pipeworks.adapters.memory import InMemoryBacklog, InMemoryRecorder, NoOpAgent
from pipeworks.core.models import AcceptanceCriterion, Task
from pipeworks.harness.gates import CompositeHarness, QualityGate, acceptance_gate
from pipeworks.loop.engine import LoopEngine


def build_demo_engine() -> LoopEngine:
    task = Task(
        id="SDK-001",
        title="Bootstrap agent loop SDK foundation",
        priority=1,
        acceptance=[
            AcceptanceCriterion(
                id="SDK-001-AC1",
                statement="Loop engine selects one unblocked task and records evidence.",
            )
        ],
    )
    return LoopEngine(
        backlog=InMemoryBacklog([task]),
        agent=NoOpAgent(),
        harness=CompositeHarness([QualityGate("acceptance", acceptance_gate)]),
        recorder=InMemoryRecorder(),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Pipe Works agent loop harness.")
    parser.add_argument("--once", action="store_true", help="Run one loop iteration.")
    args = parser.parse_args()

    if args.once:
        decision = build_demo_engine().run_once()
        print(f"{decision.reason} task={decision.task_id}")
        return 0 if decision.task_id else 1

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
