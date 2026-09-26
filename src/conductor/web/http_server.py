import asyncio
import os
import uvicorn
import logging
from typing import Any
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi import WebSocket
from fastapi.websockets import WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
from starlette.concurrency import run_in_threadpool

from conductor.domain.supervisor import ProcessLookupError as SupervisorProcessLookupError
from conductor.domain.supervisor import Supervisor
from conductor.repository.database import Database
from pipeline.arguments import PipelineArguments, parse_arguments
from conductor.web.statistics_hub import StatisticsHub
from conductor.web.log_hub import LogHub

logger = logging.getLogger(__name__)


class HttpServer:
    def __init__(
        self,
        port: int,
        supervisor: Supervisor,
        database: Database,
        host: str = "127.0.0.1",
    ) -> None:
        self._port = port
        self._host = host
        self.supervisor = supervisor
        self.database = database
        self._statistics_hub = StatisticsHub()
        self._log_hub = LogHub()
        self._web_root = Path(__file__).parent
        self._app = FastAPI()

        @self._app.get("/", include_in_schema=False)
        def index() -> FileResponse:
            return FileResponse(self._web_root / "static" / "index.html")

        @self._app.post("/api/processes", status_code=201)
        def create_process(payload: dict[str, Any]) -> dict[str, object]:
            description = _parse_description(payload)
            process_id = payload.get("process_id")
            auto_start = payload.get("auto_start")
            if not isinstance(process_id, str) or not process_id.strip():
                raise HTTPException(status_code=422, detail="process_id는 필수입니다.")
            if not isinstance(auto_start, bool):
                raise HTTPException(status_code=422, detail="auto_start는 true 또는 false여야 합니다.")
            try:
                parameters = _parse_pipeline_parameters(payload)
            except (SystemExit, ValueError) as error:
                raise HTTPException(status_code=422, detail=str(error)) from error

            self.database.save_process(process_id, auto_start, parameters, description)
            saved = self.database.get_process(process_id)
            if saved is None:
                raise HTTPException(status_code=500, detail="프로세스 저장에 실패했습니다.")
            return saved

        @self._app.get("/api/processes")
        def list_processes() -> list[dict[str, object]]:
            return self.database.list_processes()

        @self._app.put("/api/processes/order")
        def reorder_processes(payload: dict[str, Any]) -> dict[str, list[str]]:
            process_ids = payload.get("process_ids")
            if not isinstance(process_ids, list) or any(
                not isinstance(process_id, str) for process_id in process_ids
            ):
                raise HTTPException(
                    status_code=422,
                    detail="process_ids must be a list of process ID strings.",
                )
            try:
                self.database.reorder_processes(process_ids)
            except ValueError as error:
                raise HTTPException(status_code=409, detail=str(error)) from error
            return {"process_ids": process_ids}

        @self._app.get("/api/processes/status")
        async def get_process_status(
            process_id: str | None = None,
        ) -> dict[str, object]:
            if process_id is not None:
                if self.database.get_process(process_id) is None:
                    raise HTTPException(
                        status_code=404, detail="저장된 프로세스를 찾을 수 없습니다."
                    )
                try:
                    is_running = await run_in_threadpool(
                        self.supervisor.is_process_running, process_id
                    )
                except SupervisorProcessLookupError as error:
                    logger.warning("OS 프로세스 상태 조회 실패: %s", error)
                    raise HTTPException(
                        status_code=503,
                        detail="OS process state could not be inspected.",
                    ) from error
                return {
                    "process_id": process_id,
                    "state": "running" if is_running else "stopped",
                }

            process_ids = [
                str(process["process_id"])
                for process in self.database.list_processes()
            ]
            try:
                states = await run_in_threadpool(
                    self.supervisor.get_process_states, process_ids
                )
            except SupervisorProcessLookupError as error:
                logger.warning("OS process state batch lookup failed: %s", error)
                raise HTTPException(
                    status_code=503,
                    detail="OS process state could not be inspected.",
                ) from error
            return {
                "processes": [
                    {
                        "process_id": current_id,
                        "state": "running" if states[current_id] else "stopped",
                    }
                    for current_id in process_ids
                ]
            }

        @self._app.post("/api/processes/start")
        async def start_process(process_id: str) -> dict[str, object]:
            process = self.database.get_process(process_id)
            if process is None:
                raise HTTPException(status_code=404, detail="저장된 프로세스를 찾을 수 없습니다.")
            try:
                await run_in_threadpool(self.supervisor.start_process, process)
            except ValueError as error:
                raise HTTPException(status_code=409, detail=str(error)) from error
            except OSError as error:
                logger.exception("프로세스 시작 실패: %s", process_id)
                raise HTTPException(status_code=500, detail="프로세스를 시작할 수 없습니다.") from error
            except SupervisorProcessLookupError as error:
                raise HTTPException(
                    status_code=503,
                    detail="OS 프로세스 상태를 확인할 수 없습니다.",
                ) from error
            return {"process_id": process_id, "state": "running"}

        @self._app.post("/api/processes/stop")
        async def stop_process(process_id: str) -> dict[str, str]:
            try:
                stopped = await run_in_threadpool(
                    self.supervisor.stop_process, process_id
                )
            except SupervisorProcessLookupError as error:
                raise HTTPException(
                    status_code=503,
                    detail="OS 프로세스 상태를 확인할 수 없습니다.",
                ) from error
            if not stopped:
                raise HTTPException(status_code=404, detail="실행 중인 프로세스를 찾을 수 없습니다.")
            return {"process_id": process_id, "state": "stopped"}

        @self._app.put("/api/processes")
        def update_process(
            process_id: str, payload: dict[str, Any]
        ) -> dict[str, object]:
            description = _parse_description(payload)
            payload_process_id = payload.get("process_id")
            if payload_process_id != process_id:
                raise HTTPException(status_code=422, detail="요청 경로와 process_id가 일치하지 않습니다.")
            if self.database.get_process(process_id) is None:
                raise HTTPException(status_code=404, detail="저장된 프로세스를 찾을 수 없습니다.")

            auto_start = payload.get("auto_start")
            if not isinstance(auto_start, bool):
                raise HTTPException(status_code=422, detail="auto_start는 true 또는 false여야 합니다.")
            try:
                parameters = _parse_pipeline_parameters(payload)
            except (SystemExit, ValueError) as error:
                raise HTTPException(status_code=422, detail=str(error)) from error

            self.database.save_process(process_id, auto_start, parameters, description)
            saved = self.database.get_process(process_id)
            if saved is None:
                raise HTTPException(status_code=500, detail="프로세스 수정에 실패했습니다.")
            return saved

        @self._app.delete("/api/processes", status_code=204)
        def delete_process(process_id: str) -> None:
            if not self.database.delete_process(process_id):
                raise HTTPException(status_code=404, detail="저장된 프로세스를 찾을 수 없습니다.")
            self._log_hub.remove_process(process_id)

        @self._app.post("/api/processes/open-module")
        async def open_module(process_id: str, stage: str) -> dict[str, str]:
            module_fields = {
                "metadata": "metadata_path",
                "inference": "inference_path",
                "postprocess": "postprocess_path",
            }
            field = module_fields.get(stage)
            if field is None:
                raise HTTPException(
                    status_code=422, detail="Unsupported module stage."
                )

            process = await run_in_threadpool(self.database.get_process, process_id)
            if process is None:
                raise HTTPException(status_code=404, detail="Process was not found.")
            module_path = process.get(field)
            if not isinstance(module_path, str) or not module_path.strip():
                raise HTTPException(
                    status_code=404, detail="No module file is configured."
                )

            path = Path(module_path).expanduser()
            if not path.is_absolute():
                path = Path.cwd() / path
            try:
                resolved_path = path.resolve(strict=True)
            except (OSError, RuntimeError) as error:
                raise HTTPException(
                    status_code=404, detail="Module file was not found."
                ) from error
            if not resolved_path.is_file() or resolved_path.suffix.casefold() != ".py":
                raise HTTPException(
                    status_code=422,
                    detail="Module path must point to a Python file.",
                )

            open_with_default_app = getattr(os, "startfile", None)
            if open_with_default_app is None:
                raise HTTPException(
                    status_code=501,
                    detail="Opening files with the default app is supported on Windows only.",
                )
            try:
                await run_in_threadpool(open_with_default_app, str(resolved_path))
            except OSError as error:
                logger.exception("Could not open module file: %s", resolved_path)
                raise HTTPException(
                    status_code=500, detail="Could not open module file."
                ) from error
            return {"path": str(resolved_path)}

        @self._app.websocket("/ws/pipeline-stats")
        async def receive_pipeline_statistics(websocket: WebSocket) -> None:
            await websocket.accept()
            try:
                while True:
                    message = await websocket.receive_json()
                    update = StatisticsHub.parse_update(message)
                    if update is None:
                        logger.warning("잘못된 통계 WebSocket 메시지를 무시합니다.")
                        continue
                    process_id, values = update
                    if await run_in_threadpool(
                        self.database.get_process, process_id
                    ) is None:
                        continue
                    self._statistics_hub.publish(process_id, values)
            except WebSocketDisconnect:
                return

        @self._app.websocket("/ws/process-stats")
        async def stream_process_statistics(websocket: WebSocket) -> None:
            await self._statistics_hub.stream_to_browser(websocket)

        @self._app.websocket("/ws/pipeline-logs")
        async def receive_pipeline_logs(websocket: WebSocket) -> None:
            await websocket.accept()
            process_id = websocket.query_params.get("process_id")
            if (
                not process_id
                or await run_in_threadpool(
                    self.database.get_process, process_id
                ) is None
            ):
                await websocket.close(code=1008)
                return
            try:
                while True:
                    message = await websocket.receive_json()
                    update = LogHub.parse_update(message)
                    if update is None or update[0] != process_id:
                        logger.warning("잘못된 파이프라인 로그 WebSocket 메시지를 무시합니다.")
                        continue
                    _, event = update
                    self._log_hub.publish(process_id, event)
            except WebSocketDisconnect:
                return

        @self._app.websocket("/ws/process-logs")
        async def stream_process_logs(
            websocket: WebSocket, process_id: str
        ) -> None:
            if await run_in_threadpool(
                self.database.get_process, process_id
            ) is None:
                await websocket.close(code=1008)
                return
            await self._log_hub.stream_to_browser(websocket, process_id)

        @self._app.websocket("/ws/process-status")
        async def stream_process_status(websocket: WebSocket) -> None:
            await websocket.accept()
            try:
                while True:
                    saved_processes = await run_in_threadpool(
                        self.database.list_processes
                    )
                    process_ids = [
                        str(process["process_id"]) for process in saved_processes
                    ]
                    try:
                        states = await run_in_threadpool(
                            self.supervisor.get_process_states, process_ids
                        )
                    except SupervisorProcessLookupError as error:
                        logger.warning("OS process state WebSocket lookup failed: %s", error)
                        await asyncio.sleep(1.0)
                        continue
                    await websocket.send_json(
                        {
                            "processes": [
                                {
                                    "process_id": process_id,
                                    "state": "running" if states[process_id] else "stopped",
                                }
                                for process_id in process_ids
                            ]
                        }
                    )
                    await asyncio.sleep(1.0)
            except WebSocketDisconnect:
                return

        self._app.mount(
            "/",
            StaticFiles(directory=self._web_root / "static"),
            name="static",
        )

    def start(self) -> None:
        uvicorn.run(
            self._app,
            host=self._host,
            port=self._port,
            reload=False,
        )


def _parse_pipeline_parameters(payload: dict[str, Any]) -> PipelineArguments:
    required = (
        "input_rtsp_url",
        "input_rtsp_transport",
        "output_rtsp_url",
        "output_rtsp_transport",
        "pipe_type",
        "metadata_enabled",
        "inference_enabled",
        "postprocess_enabled",
    )
    arguments: list[str] = []
    for field in required:
        value = payload.get(field)
        if value is None:
            raise ValueError(f"{field}는 필수입니다.")
        arguments.extend((f"--{field.replace('_', '-')}", _argument_value(value)))

    for field in (
        "gpuid",
        "fps",
        "metadata_path",
        "inference_path",
        "inference_interval",
        "inference_frame",
        "postprocess_path",
        "log_level",
    ):
        value = payload.get(field)
        if value is not None and value != "":
            arguments.extend((f"--{field.replace('_', '-')}", _argument_value(value)))
    return parse_arguments(arguments)


def _argument_value(value: object) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def _parse_description(payload: dict[str, Any]) -> str:
    description = payload.get("description", "")
    if not isinstance(description, str):
        raise HTTPException(status_code=422, detail="description must be a string.")
    return description
