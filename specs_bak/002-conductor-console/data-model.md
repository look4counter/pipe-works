# 데이터 모델: Conductor 프로세스 관리

## 영속 프로세스 정의

SQLite `processes` 테이블의 현재 열은 다음과 같다.

| 속성 | 저장 형식 | 규칙 |
|---|---|---|
| `process_id` | TEXT | 기본 키, 공백 불가 |
| `auto_start` | INTEGER | 0 or 1; controls restart after unexpected exit for processes explicitly started through this Conductor instance |
| `input_rtsp_url`, `output_rtsp_url` | TEXT | 필수, CLI 파서 검증 |
| `input_rtsp_transport`, `output_rtsp_transport` | TEXT | 필수 문자열 |
| `pipe_type` | TEXT | `nvidia` or `bypass` |
| `gpu_id` | INTEGER | NVIDIA GPU 번호; 생략하면 0 |
| `fps` | INTEGER | 양의 정수; 비어 있으면 30으로 저장 |
| `metadata_enabled`, `inference_enabled`, `postprocess_enabled` | INTEGER | 0 또는 1 |
| 각 `*_path` | TEXT 또는 NULL | 사용자 단계 Python 경로 |
| `inference_interval` | INTEGER | 양의 정수; 비어 있으면 3으로 저장 |
| `inference_frame` | TEXT or NULL | `pytorch` or NULL; historical `onnx` values are normalized to `pytorch` on database startup |
| `log_level` | TEXT | One of `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`; defaults to `INFO` |

SQLite 연결은 저장 후 커밋하고 예외 시 롤백한다. 기존 DB에 FPS 열이 없으면 초기화 시 기본값 30을 갖는 열을 추가하며, FPS 또는 추론 간격이 기존 행에서 NULL이면 각각 30 또는 3으로 채운다. 기존 CPU pipe type 행은 NVIDIA로, 비어 있는 GPU ID는 0으로, ONNX FRAME TYPE은 pytorch로 초기화 시 변환한다. `process_id` 충돌 저장은 설정을 갱신하는 upsert다.
목록은 `process_id` 순서로 반환한다. DB에는 런타임 PID 또는 실행 상태를 저장하지 않는다.

## 런타임 상태
Runtime state is not persisted. `Supervisor` derives it from the Windows process command line and `--process-id`.
The only process states are `running` and `stopped`. HTTP status endpoints return 503 when OS inspection fails; the status WebSocket skips that update and retries on its next poll.

실행 상태는 영속 엔터티가 아니다. `Supervisor`가 Windows 프로세스 명령행에서 파이프라인 모듈과
`--process-id` 값을 확인해 `running` 또는 `stopped`를 계산한다. 프로세스 탐색 실패를 별도 오류 상태로
표현하는 기능은 아직 없다.

## 사용자 인터페이스 모델

The static UI presents process ID, pipe type, enabled user stages, input/output URLs, live counters, process state, and recent/live logs. Statistics and logs arrive over separate WebSockets.


## Runtime and migration details
Runtime state is not persisted. `Supervisor` derives it from the Windows process command line and `--process-id`.
The only process states are `running` and `stopped`. HTTP status endpoints return 503 when OS inspection fails; the status WebSocket skips that update and retries on its next poll.

The `auto_start` field is persisted as SQLite integer 0/1 and converted to Python boolean in API records. The database does not persist a runtime PID. Process configuration writes use an upsert; transaction errors roll back. Startup adds a missing `fps` column with default 30, fills NULL `fps` and `inference_interval` with 30 and 3, maps unsupported historical pipe types to `nvidia`, fills missing GPU IDs with 0, and maps historical ONNX frame selections to `pytorch`. A historical `runtime_pid` column is cleared if present; it is not used as process-state evidence.

The current SQLite table constraint accepts only `nvidia` and `bypass`. On startup, a table definition without `bypass` is rebuilt with the current constraint. Existing rows are copied; unsupported historical pipe types are normalized to `nvidia`, and historical ONNX frame selections are normalized to `pytorch`. `CREATE TABLE IF NOT EXISTS` alone does not change an existing table, so this explicit rebuild is required.

The log_level field is persisted as text with default INFO and a check constraint for the five supported levels. Startup adds this column to older databases and normalizes missing or unsupported historical values to INFO. The process editor exposes it and the supervisor passes it to the child pipeline as --log-level.
