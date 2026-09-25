import pytest

from conductor.cli import parse_arguments


def test_conductor_cli_accepts_host_and_port() -> None:
    arguments = parse_arguments(["--host", "0.0.0.0", "--port", "8080"])

    assert arguments.host == "0.0.0.0"
    assert arguments.port == 8080


@pytest.mark.parametrize("port", ["0", "-1", "65536", "not-a-port"])
def test_conductor_cli_rejects_invalid_ports(port: str) -> None:
    with pytest.raises(SystemExit):
        parse_arguments(["--port", port])
