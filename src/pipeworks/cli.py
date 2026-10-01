"""Command line entry point for the Pipe Works loop harness."""

from __future__ import annotations

import argparse
from pathlib import Path

from pipeworks import __version__
from pipeworks.adapters.memory import InMemoryBacklog, InMemoryRecorder, NoOpAgent
from pipeworks.core.models import AcceptanceCriterion, Task
from pipeworks.harness.gates import (
    CommandGate,
    CompositeHarness,
    QualityGate,
    acceptance_gate,
    ruff_gate,
)
from pipeworks.loop.engine import LoopEngine
from pipeworks.templates import STARTER_CONFIG, STARTER_PIPELINE


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
    parser.add_argument("--version", action="version", version=f"pipe-works {__version__}")
    parser.add_argument("--once", action="store_true", help="Run one loop iteration.")
    parser.add_argument("--check", action="store_true", help="Run local SDK quality gates.")
    parser.add_argument("--init-example", metavar="DIR", help="Create a starter pipeline project.")
    args = parser.parse_args()

    if args.check:
        return run_checks()

    if args.init_example:
        init_example(Path(args.init_example))
        return 0

    if args.once:
        decision = build_demo_engine().run_once()
        print(f"{decision.reason} task={decision.task_id}")
        return 0 if decision.task_id else 1

    parser.print_help()
    return 0


def run_checks() -> int:
    task = Task(
        id="CHECK",
        title="Run local SDK checks",
        priority=1,
        acceptance=[AcceptanceCriterion("CHECK-AC1", "Quality gates pass.")],
    )
    gates = [
        ruff_gate(
            "src/pipeworks",
            "tests/sdk",
            "examples/01_single_stream_rtsp_style.py",
            "examples/02_multistream_batch.py",
            "examples/03_multistage_inference.py",
            "examples/04_custom_component.py",
            "examples/05_local_synthetic_config.py",
        ),
        CommandGate(
            name="pytest",
            command=(
                "python",
                "-m",
                "pytest",
                "-q",
                "tests/sdk",
                "--ignore=tests/sdk/test_cli_checks.py",
            ),
            timeout_s=60,
        ),
    ]
    results = [gate.run(task) for gate in gates]
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        print(f"{status} {result.name}: {result.evidence[0].summary}")
    return 0 if all(result.passed for result in results) else 1


def init_example(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    files = {
        directory / "pipeline.py": STARTER_PIPELINE,
        directory / "pipeworks.yaml": STARTER_CONFIG,
    }
    existing = [path for path in files if path.exists()]
    if existing:
        existing_names = ", ".join(path.name for path in existing)
        raise FileExistsError(f"refusing to overwrite existing files: {existing_names}")
    for path, content in files.items():
        path.write_text(content, encoding="utf-8")
    print(f"Created starter Pipe Works project in {directory}")


if __name__ == "__main__":
    raise SystemExit(main())
