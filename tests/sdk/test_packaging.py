import subprocess
import sys

import pipeworks


def test_package_exposes_version() -> None:
    assert pipeworks.__version__ == "0.1.0"


def test_cli_exposes_version() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "pipeworks.cli", "--version"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "pipe-works 0.1.0" in completed.stdout
