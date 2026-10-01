from pipeworks import cli


def test_run_checks_passes_for_current_sdk() -> None:
    assert cli.run_checks() == 0
