import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = [
    ROOT / "examples" / "01_single_stream_rtsp_style.py",
    ROOT / "examples" / "02_multistream_batch.py",
    ROOT / "examples" / "03_multistage_inference.py",
    ROOT / "examples" / "04_custom_component.py",
    ROOT / "examples" / "05_local_synthetic_config.py",
]


@pytest.mark.parametrize("example", EXAMPLES, ids=lambda path: path.name)
def test_curated_example_executes(example: Path) -> None:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src")

    completed = subprocess.run(
        [sys.executable, str(example)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        check=False,
        text=True,
        timeout=10,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip()


def test_official_examples_include_external_config_samples() -> None:
    config_dir = ROOT / "examples" / "config"
    assert {
        "single_stream.yaml",
        "multistream_batch.yaml",
        "local_pipeline.yaml",
    } <= {path.name for path in config_dir.glob("*.yaml")}
