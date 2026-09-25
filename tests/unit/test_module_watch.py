from pathlib import Path
import os

from pipeline.cli import load_stage_module, watch_module


class PollThenStop:
    def __init__(self, polls: int) -> None:
        self.polls = polls
        self.count = 0

    def wait(self, timeout: float) -> bool:
        self.count += 1
        return self.count > self.polls


def test_watch_module_reloads_changed_file(tmp_path: Path) -> None:
    module_path = tmp_path / "stage.py"
    module_path.write_text("VALUE = 1\n", encoding="utf-8")
    previous_mtime = module_path.stat().st_mtime_ns
    original_module = load_stage_module(module_path, "inference")
    module_path.write_text("VALUE = 2\n", encoding="utf-8")
    changed_mtime = previous_mtime + 2_000_000_000
    os.utime(module_path, ns=(changed_mtime, changed_mtime))
    module_state = {"inference": original_module}
    stop_event = PollThenStop(1)

    watch_module(
        module_path, "inference", module_state, stop_event, previous_mtime
    )

    assert module_state["inference"] is not original_module
    assert module_state["inference"].VALUE == 2


def test_watch_module_keeps_previous_value_and_retries_failed_reload(
    monkeypatch, tmp_path: Path
) -> None:
    module_path = tmp_path / "stage.py"
    module_path.write_text("value = 1", encoding="utf-8")
    previous_mtime = module_path.stat().st_mtime_ns
    module_path.write_text("value = 2", encoding="utf-8")
    os.utime(module_path, ns=(previous_mtime + 1_000_000, previous_mtime + 1_000_000))
    module_state = {"postprocess": "old-module"}
    stop_event = PollThenStop(2)
    attempts = 0

    def load_stage(*_):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            assert module_state["postprocess"] == "old-module"
            raise SyntaxError("partial file write")
        return "new-module"

    monkeypatch.setattr("pipeline.cli.load_stage_module", load_stage)

    watch_module(
        module_path, "postprocess", module_state, stop_event, previous_mtime
    )

    assert attempts == 2
    assert module_state["postprocess"] == "new-module"
