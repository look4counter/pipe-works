import asyncio
from threading import Event

from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
import pytest


def process_payload() -> dict[str, object]:
    return {
        "process_id": "camera-001",
        "auto_start": False,
        "input_rtsp_url": "rtsp://camera/input",
        "input_rtsp_transport": "tcp",
        "output_rtsp_url": "rtsp://server/output",
        "output_rtsp_transport": "tcp",
        "pipe_type": "nvidia",
        "gpuid": 0,
        "metadata_enabled": False,
        "inference_enabled": False,
        "postprocess_enabled": False,
    }


def test_static_page_and_process_crud_api(http_server, database) -> None:
    with TestClient(http_server._app) as client:
        page = client.get("/")
        assert page.status_code == 200
        assert "text/html" in page.headers["content-type"]

        created = client.post("/api/processes", json=process_payload())
        assert created.status_code == 201
        assert created.json()["process_id"] == "camera-001"
        assert created.json()["gpu_id"] == 0

        listed = client.get("/api/processes")
        assert listed.status_code == 200
        assert [item["process_id"] for item in listed.json()] == ["camera-001"]

        updated_payload = process_payload()
        updated_payload["auto_start"] = True
        updated_payload["fps"] = 24
        updated = client.put(
            "/api/processes", params={"process_id": "camera-001"}, json=updated_payload
        )
        assert updated.status_code == 200
        assert updated.json()["auto_start"] is True
        assert updated.json()["fps"] == 24

        deleted = client.delete("/api/processes", params={"process_id": "camera-001"})
        assert deleted.status_code == 204
        assert database.get_process("camera-001") is None


def test_process_api_rejects_invalid_pipeline_configuration(http_server) -> None:
    payload = process_payload()
    payload["pipe_type"] = "cpu"

    with TestClient(http_server._app) as client:
        response = client.post("/api/processes", json=payload)

    assert response.status_code == 422


def test_process_status_api_returns_error_when_os_query_fails(
    http_server, monkeypatch
) -> None:
    with TestClient(http_server._app) as client:
        created = client.post("/api/processes", json=process_payload())
        assert created.status_code == 201

        def fail_lookup(_process_ids):
            from conductor.domain.supervisor import ProcessLookupError

            raise ProcessLookupError("access denied")

        monkeypatch.setattr(
            http_server.supervisor, "get_process_states", fail_lookup
        )
        response = client.get("/api/processes/status")
        monkeypatch.setattr(
            http_server.supervisor, "is_process_running", fail_lookup
        )
        single_response = client.get(
            "/api/processes/status", params={"process_id": "camera-001"}
        )

    assert response.status_code == 503
    assert single_response.status_code == 503


@pytest.mark.anyio
@pytest.mark.parametrize("operation", ["status", "start", "stop"])
async def test_slow_supervisor_operation_does_not_block_other_api_requests(
    http_server, monkeypatch, operation: str
) -> None:
    started = Event()
    release = Event()

    def slow_operation(*_args) -> bool | int:
        started.set()
        if not release.wait(timeout=5):
            raise TimeoutError("test did not release the Supervisor operation")
        return 1234 if operation == "start" else True

    method_by_operation = {
        "status": "is_process_running",
        "start": "start_process",
        "stop": "stop_process",
    }
    monkeypatch.setattr(
        http_server.supervisor, method_by_operation[operation], slow_operation
    )

    async with AsyncClient(
        transport=ASGITransport(app=http_server._app), base_url="http://test"
    ) as client:
        created = await client.post("/api/processes", json=process_payload())
        assert created.status_code == 201

        route = {
            "status": ("GET", "/api/processes/status"),
            "start": ("POST", "/api/processes/start"),
            "stop": ("POST", "/api/processes/stop"),
        }[operation]
        operation_task = asyncio.create_task(
            client.request(
                route[0], route[1], params={"process_id": "camera-001"}
            )
        )
        assert await asyncio.to_thread(started.wait, timeout=2)

        try:
            listing = await asyncio.wait_for(client.get("/api/processes"), timeout=1)
            assert listing.status_code == 200
        finally:
            release.set()

        response = await asyncio.wait_for(operation_task, timeout=2)
        assert response.status_code == 200
        expected_state = "stopped" if operation == "stop" else "running"
        assert response.json()["state"] == expected_state
