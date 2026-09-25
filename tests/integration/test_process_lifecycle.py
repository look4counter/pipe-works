import subprocess
import sys
from uuid import uuid4

from fastapi.testclient import TestClient

from conductor.domain.supervisor import Supervisor
from conductor.repository.database import Database
from conductor.web.http_server import HttpServer
from pipeline.arguments import PipelineArguments


def test_restarted_conductor_finds_and_stops_existing_pipeline(
    tmp_path, monkeypatch
) -> None:
    process_id = f"lifecycle-{uuid4().hex}"
    database_path = tmp_path / "lifecycle.sqlite3"
    database = Database(database_path)
    parameters = PipelineArguments(
        "rtsp://127.0.0.1/input",
        "tcp",
        "rtsp://127.0.0.1/output",
        "tcp",
        "nvidia",
        0,
        False,
        None,
        False,
        None,
        3,
        None,
        False,
        None,
    )
    database.save_process(process_id, False, parameters)

    # Keep a real child process alive, without starting a GPU pipeline.
    process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(120)"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    def find_test_process(_supervisor, requested_process_id):
        if requested_process_id == process_id and process.poll() is None:
            return process.pid
        return None

    def terminate_test_process(command, **_kwargs):
        assert command == ["taskkill", "/PID", str(process.pid), "/T", "/F"]
        process.terminate()
        process.wait(timeout=5)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(Supervisor, "_find_process_pid", find_test_process)
    monkeypatch.setattr(
        "conductor.domain.supervisor.subprocess.run", terminate_test_process
    )
    try:
        # Recreate the database repository and HTTP server as if Conductor restarted.
        restarted_database = Database(database_path)
        restarted_server = HttpServer(
            port=0,
            supervisor=Supervisor(),
            database=restarted_database,
        )
        with TestClient(restarted_server._app) as client:
            status = client.get(
                "/api/processes/status", params={"process_id": process_id}
            )
            assert status.status_code == 200
            assert status.json() == {"process_id": process_id, "state": "running"}

            stopped = client.post(
                "/api/processes/stop", params={"process_id": process_id}
            )
            assert stopped.status_code == 200
            assert stopped.json() == {"process_id": process_id, "state": "stopped"}

        process.wait(timeout=10)
        assert process.poll() is not None
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
