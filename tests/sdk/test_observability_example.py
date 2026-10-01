import os
import subprocess
import sys
from pathlib import Path


def test_observability_example_runs_once() -> None:
    root = Path(__file__).resolve().parents[2]
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root / "src")
    completed = subprocess.run(
        [sys.executable, str(root / "examples" / "06_observability_server.py"), "--once"],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )

    assert completed.returncode == 0, completed.stderr
    assert "frames_processed" in completed.stdout
