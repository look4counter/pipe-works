import pytest

from conductor.repository.database import Database
from conductor.domain.supervisor import Supervisor
from conductor.web.http_server import HttpServer


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def database(tmp_path):
    return Database(tmp_path / "test.sqlite3")


@pytest.fixture
def supervisor():
    return Supervisor()


@pytest.fixture
def http_server(database, supervisor):
    return HttpServer(port=0, supervisor=supervisor, database=database)
