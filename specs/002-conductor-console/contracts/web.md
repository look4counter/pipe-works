# 웹 계약: Conductor 콘솔 및 프로세스 관리

구현 기준: `src/conductor/web/http_server.py`. 요청 본문은 JSON 객체이며 저장 파라미터는 001 CLI 계약으로 검증한다. `fps`는 선택 양의 정수이며 생략·null·빈 문자열이면 30, `inference_interval`은 같은 경우 3으로 저장된다.

| 요청 | 성공 결과 | 실패 결과 |
|---|---|---|
| `GET /` | `static/index.html` | 프레임워크 오류 |
| `GET /index.css`, `GET /index.js` | 정적 파일 | 파일 없음 응답 |
| `GET /api/processes` | 저장된 정의의 JSON 배열 | 저장소 오류 |
| `POST /api/processes` | 저장 또는 기존 ID upsert, 201과 정의 응답 | 입력 오류 422 |
| `PUT /api/processes?process_id={id}` | 같은 ID 정의 수정 후 JSON 응답 | 경로·본문 ID 불일치 또는 입력 오류 422, 미존재 404 |
| `DELETE /api/processes?process_id={id}` | 정의 삭제, 204 | 미존재 404 |
| `GET /api/processes/status?process_id={id}` | `{process_id, state}`; state is `running` or `stopped` | Definition not found 404, OS inspection failure 503 |
| `POST /api/processes/start?process_id={id}` | 하위 파이프라인 시작 후 `{process_id, state: running}` | 미존재 404, 중복 409, OS 시작 오류 500 |
| `POST /api/processes/stop?process_id={id}` | 일치 프로세스 트리 강제 종료 후 `{process_id, state: stopped}` | 실행 프로세스 미발견 404 |
The process-start API passes the Conductor HTTP port to the child as `PIPE_WORKS_CONDUCTOR_PORT`; the pipeline uses it for the default statistics and log WebSocket connections.
Process definitions accept `log_level` with values `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL`, defaulting to `INFO`; it is forwarded to the child as `--log-level`.

`POST` 시작은 저장된 정의를 조회해 `python -m pipeline.cli --process-id {id}`와 모든 파이프라인 파라미터를
The server starts the saved `nvidia` or `bypass` pipeline and passes its configuration as CLI arguments. Pipeline behavior and limitations are specified in feature 001. Stop uses Windows process command-line matching and `taskkill /PID {pid} /T /F`.
The supervisor finds the matching process before invoking the force-stop command.

Process state is derived from OS enumeration and has only two values: `running` and `stopped`. HTTP status inspection failures return 503. The WebSocket contracts and in-memory buffering limits are defined below.

## WebSocket message and buffering contract

- `/ws/pipeline-stats` accepts process IDs, nonnegative integer values for `received`, `sent`, `anomalous`, `inferenceFailed`, and `postprocessFailed`, and nullable finite nonnegative numeric `average_ms`. Malformed messages are ignored; updates for definitions no longer in the database are ignored. `average_ms` measures NVIDIA decoder API start to encoder API return per frame, excludes packet wrapping and output/network send, and is null for bypass.
- `/ws/process-stats` sends the latest in-memory snapshot for each process on connection, then streams newer snapshots. Per-client queues hold at most 256 updates and discard the oldest queued update when full.
- `/ws/pipeline-logs?process_id=...` accepts log records only for an existing process and only when the message process ID matches the connection query. A log record has numeric `created_at`, string `level`, `logger`, and `message`, and optional string `exception`; field lengths are capped by the server.
- `/ws/process-logs?process_id=...` requires an existing process, first sends its retained history, then streams live entries. History is capped at 500 records per process; each client queue is capped at 256 and drops the oldest record under backpressure. Deleting a definition removes its retained log history.
- `/ws/process-status` polls Windows process state once per second and sends the complete list. On OS inspection failure, it logs the error, skips that update, and retries on the next interval. Single and aggregate HTTP status endpoints return 503 on OS inspection failure.

`POST /api/processes/open-module?process_id={id}&stage={metadata|inference|postprocess}` opens the selected configured module path. Invalid stages and paths that do not point to a Python file return 422; missing definitions, unconfigured module paths, and missing files return 404; non-Windows platforms return 501; an OS file-opener failure returns 500. Success returns the resolved path.
