import os
import subprocess
import sys
from pathlib import Path

from pipeworks.cli import init_example

ROOT = Path(__file__).resolve().parents[2]


def test_init_example_creates_runnable_pipeline(tmp_path) -> None:
    init_example(tmp_path)

    assert (tmp_path / "pipeline.py").exists()
    assert (tmp_path / "pipeworks.yaml").exists()

    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src")
    completed = subprocess.run(
        [sys.executable, str(tmp_path / "pipeline.py")],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        check=False,
        text=True,
        timeout=10,
    )

    assert completed.returncode == 0, completed.stderr
    assert "Pipeline: starter-cobble" in completed.stdout
