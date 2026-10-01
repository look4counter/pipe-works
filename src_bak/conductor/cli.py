import argparse
import logging
import os
from collections.abc import Sequence

from conductor.domain.supervisor import Supervisor
from conductor.repository.database import Database
from conductor.web.http_server import HttpServer

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(name)s][%(levelname)s] %(message)s",
)


def _valid_port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("포트는 정수여야 합니다.") from error
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("포트는 1부터 65535 사이여야 합니다.")
    return port


def parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pipe Works Conductor 웹 서버")
    parser.add_argument(
        "--host",
        default=os.environ.get("PIPE_WORKS_HOST", "127.0.0.1"),
        help="바인딩할 주소 (기본값: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=_valid_port,
        default=os.environ.get("PIPE_WORKS_PORT", "8000"),
        help="바인딩할 포트 (기본값: 8000)",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    arguments = parse_arguments(argv)
    database = Database()
    supervisor = Supervisor(conductor_port=arguments.port)
    supervisor.start_auto_start_monitor(database)
    try:
        HttpServer(arguments.port, supervisor, database, host=arguments.host).start()
    except (OSError, SystemExit) as error:
        if isinstance(error, SystemExit) and error.code in (None, 0):
            raise
        logger.error(
            "Conductor 서버 시작 실패 (%s:%s): 포트가 사용 중이거나 주소에 바인딩할 수 없습니다.",
            arguments.host,
            arguments.port,
        )
        raise SystemExit(1) from None
    finally:
        supervisor.stop_auto_start_monitor()


if __name__ == "__main__":
    main()
