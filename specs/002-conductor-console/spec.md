# 기능 명세: Conductor 콘솔 및 프로세스 관리

**기능 경로**: `002-conductor-console`  
**작성일**: 2026-09-23  
**상태**: 로컬 CRUD·수동 프로세스 제어·NVIDIA 파이프라인·사용자 시작 프로세스 자동 복구·파이프라인 카운터·상태·로그 WebSocket 구현

## 목적과 현재 구현 범위

Conductor provides a browser console and HTTP API, stores `nvidia` and `bypass` pipeline settings in SQLite, and controls configured pipeline processes on Windows.
Runtime state is derived from the Windows process command line and `--process-id`; media behavior and limitations follow [spec 001](../001-media-pipeline/spec.md).

## 사용자 시나리오 및 테스트

### 사용자 스토리 1 - 프로세스 설정 관리 (우선순위: P1, 구현됨)

운영자는 로컬 콘솔에서 파이프라인 실행 설정과 자동 시작 플래그를 등록·조회·수정·삭제한다.

**인수 시나리오**:

1. **Given** 필수 필드가 유효한 설정, **When** 운영자가 저장하면, **Then** 설정이 SQLite에 저장되고 목록에 나타난다.
2. **Given** 저장된 정의, **When** 운영자가 편집해 저장하면, **Then** 동일한 `process_id`의 설정이 갱신된다.
3. **Given** 저장된 정의, **When** 운영자가 삭제를 확인하면, **Then** 정의가 데이터베이스에서 제거된다.
4. **Given** 필수 파라미터가 누락되거나 잘못된 설정, **When** API에 저장하면, **Then** 검증 오류가 반환된다.

### 사용자 스토리 2 - Windows 파이프라인 프로세스 제어 (우선순위: P1, 구현됨)

운영자는 저장된 정의를 시작·정지하고 실행 중인 상태를 확인한다.

**인수 시나리오**:

1. **Given** 저장된 정의가 실행 중이 아닐 때, **When** 시작 API를 호출하면, **Then** Conductor가 `python -m pipeline.cli`를 `--process-id`와 저장된 설정으로 실행한다.
2. **Given** 같은 `process_id`를 가진 파이프라인이 실행 중일 때, **When** 다시 시작하면, **Then** 중복 실행을 거부한다.
3. **Given** Conductor가 재시작된 뒤에도 파이프라인이 실행 중일 때, **When** 상태 또는 정지 API를 호출하면, **Then** Windows 명령행에서 `process_id`를 다시 찾아 처리한다.
4. **Given** 실행 중인 프로세스, **When** 정지를 확인하면, **Then** 해당 PID와 자식 프로세스 트리를 강제 종료한다.

### 사용자 스토리 3 - 운영 콘솔 접속과 설정 작업 (우선순위: P1, 구현됨)

운영자는 브라우저에서 프로세스 목록과 설정을 관리한다.

**인수 시나리오**:

1. **Given** Conductor가 포트 8000에서 시작되면, **When** 브라우저가 루트 경로에 접속하면, **Then** 정적 HTML·CSS·JavaScript가 제공된다.
2. **Given** 프로세스 정의가 저장되어 있으면, **When** 목록을 새로 불러오면, **Then** 정의와 처리 경로·사용자 단계 표시가 보인다.
3. **Given** 운영자가 시작·정지·삭제를 누르면, **When** 확인 후 요청하면, **Then** 대응 HTTP API를 호출하고 실패 응답을 화면에 표시한다.

## HTTP API 계약

모든 경로는 같은 로컬 FastAPI 서비스에 제공된다. 프로세스 설정 필드는 `process_id`, `auto_start`,
입출력 RTSP 주소·전송, `pipe_type`, `gpu_id`, 선택 `fps`, `metadata_*`, `inference_*`, `postprocess_*`다.
`pipe_type` accepts `nvidia` or `bypass`; the pipeline parser defaults GPU ID to 0. Bypass forces metadata, inference, and postprocess off.

| 메서드와 경로 | 동작 | 주요 응답 |
|---|---|---|
| `GET /` | 콘솔 HTML 제공 | HTML |
| 정적 파일 경로 | `index.css`, `index.js` 제공 | 파일 |
| `GET /api/processes` | 저장 정의 목록 | JSON 배열 |
| `POST /api/processes` | 정의 생성 또는 같은 키 upsert | 201 및 JSON 정의 |
| `PUT /api/processes?process_id=...` | 같은 키의 정의 갱신 | JSON 정의 |
| `DELETE /api/processes?process_id=...` | 정의 삭제 | 204 |
| `GET /api/processes/status` | 전체 저장 프로세스 상태 일괄 확인 | `processes` 배열 |
| `GET /api/processes/status?process_id=...` | Single-process status (compatibility endpoint) | `running` or `stopped`; HTTP 503 if OS inspection fails |
| `/ws/process-status` | 전체 저장 프로세스의 OS 실행 상태를 1초마다 브라우저에 전송 | `processes` 배열 |
| `/ws/pipeline-logs?process_id=...` | 파이프라인 로그를 Conductor에 전달 | 로그 이벤트 |
| `/ws/process-logs?process_id=...` | 해당 프로세스의 최근 로그와 새 로그를 브라우저에 전송 | 로그 이벤트 |
| `POST /api/processes/start?process_id=...` | 저장 정의 실행 | `running` 또는 오류 |
| `POST /api/processes/stop?process_id=...` | 일치 프로세스 트리 강제 종료 | `stopped` 또는 오류 |

잘못된 입력은 422, 존재하지 않는 정의·실행은 404, 중복 실행은 409로 응답한다. 실행 시작 중 일반 OS 오류는
안전한 메시지로 500 응답한다.

## 요구사항

- **FR-001**: 로컬 루트 경로와 정적 자원에서 운영 UI를 제공해야 한다. (구현됨)
- **FR-002**: 프로세스 설정 및 `auto_start` 플래그를 SQLite에 저장하고 CRUD API를 제공해야 한다. FPS를 설정한 경우에도 저장·조회되어야 한다. (구현됨)
- **FR-003**: 저장·수정 전에 입력 설정을 001 CLI 파서로 검증해야 한다. (구현됨)
- **FR-004**: Start the configured `nvidia` or `bypass` pipeline and pass saved settings, `process_id`, and the Conductor HTTP port (`PIPE_WORKS_CONDUCTOR_PORT`) to the child process. Pass `--fps` when configured. (Implemented)
- **FR-005**: Identify pipeline processes by matching `python.exe` or `pythonw.exe` command lines containing `-m pipeline.cli --process-id <id>`. Expose only `running` and `stopped` states; return API errors when OS inspection fails. (Implemented)
- **FR-006**: 정지는 일치 프로세스의 자식 트리를 `taskkill /T /F`로 종료해야 한다. (구현됨)
- **FR-007**: UI는 등록·편집·삭제·시작·정지 동작과 서버 오류를 표시해야 한다. (구현됨)
- **FR-008**: UI 편집 폼은 저장된 파이프라인 파라미터를 손실 없이 다시 채워야 한다. (구현됨; API의 `gpu_id`를 폼의 GPU ID 필드에 복원)
- **FR-009**: Conductor는 사용자가 시작한 프로세스만 재시작 후보로 추적한다. 추적 중인 프로세스가 실행되는 동안 `auto_start=true`이면 비정상 종료 후 다시 실행한다. Conductor 시작만으로 프로세스를 실행하지 않으며, 사용자가 시작하지 않은 프로세스를 자동으로 실행·복구하지 않는다. `auto_start`를 해제해도 실행 중인 프로세스는 종료하지 않고 재시작만 비활성화한다. UI/API의 명시적 정지 요청은 재시작 추적을 해제한다. (구현 완료)
- **FR-010**: 파이프라인 로그를 프로세스별 WebSocket으로 전달하고 UI에서 최근 로그와 실시간 로그를 조회할 수 있어야 한다. 파이프라인의 logging handler는 bounded queue와 전용 전송 스레드를 사용해 미디어 흐름을 기다리게 하지 않는다. (구현됨)
- **FR-011**: 수신·송신 패킷, 비정상 PTS, inference/postprocess 실패 카운터를 WebSocket으로 UI에 표시해야 한다. (구현됨)
- **FR-012**: Conductor는 bind 주소와 포트를 CLI 옵션 또는 환경 변수로 설정할 수 있고, 서버 시작 실패 시 주소·포트를 포함한 오류 메시지를 제공해야 한다. (구현됨; 기본값 `127.0.0.1:8000`)
- **FR-013**: Windows 이외 운영체제에서 시작·상태·정지 동작을 지원하거나 명확히 제한해야 한다. (Windows 전용 구현, 비Windows 동작 미지원)

## 성공 기준

- **SC-001**: 목록·상태 조회가 설정 저장소와 실행 상태 조회를 구분해 수행된다. (구현됨; 상태는 일괄 요청)
- **SC-002**: 유효한 설정은 저장되고 파서 검증 실패는 422 응답으로 거부된다.
- **SC-003**: Conductor 재시작 후에도 Windows 명령행에 식별자가 남은 파이프라인을 상태 조회·정지할 수 있다.
- **SC-004**: 중복 `process_id` 시작 요청은 이미 일치 프로세스가 확인되면 409로 거부된다.
- **SC-005**: UI가 WebSocket으로 전체 프로세스의 OS 실행 상태를 1초마다 갱신한다.

## 운영 제약과 미해결 동작

- 데이터베이스 경로는 `PIPE_WORKS_DB_PATH`로 지정할 수 있으며, 미설정 시 저장소 루트의 `pipe-works.db`를 사용한다.
- Runtime state is determined with psutil process enumeration. States are limited to `running` and `stopped`; HTTP inspection failures return 503, while WebSocket polling skips the failed update and retries on the next cycle.
- 종료는 `/F` 강제 종료이며 파이프라인의 정상 정리 절차를 기다리지 않는다.
- Supervisor는 사용자가 시작한 프로세스 ID만 메모리에 추적하고 1초마다 해당 정의의 `auto_start`와 실행 상태를 확인한다. Conductor 시작 시 기존 프로세스를 자동으로 시작하거나 추적하지 않는다. `auto_start`를 해제하면 실행 중인 프로세스는 유지하고 재시작 감시를 멈춘다. 명시적으로 정지하면 재시작 추적도 해제한다. Conductor가 재시작되면 메모리 추적은 초기화되므로 자동 복구는 Conductor가 실행 중일 때만 적용된다.
- 시작 중복 검사와 프로세스 생성은 원자적이지 않으며, 동시에 들어온 시작 요청 간 경합 가능성이 있다.
- 목록 API는 설정만 읽고, 화면은 `/ws/process-status`로 전체 상태를 받는다. Supervisor는 한 번의 OS 프로세스 순회에서 요청된 모든 `process_id`를 찾는다.
- The pipeline accepts `nvidia` and `bypass`; legacy CPU records migrate to NVIDIA/GPU 0.
- 인증·원격 공개는 제공하지 않는 로컬 단일 사용자 전제다. 로그와 실행 통계는 WebSocket으로 전달하며 Conductor 메모리에 최근 500개 로그를 프로세스별로 보관한다.

## Implemented management and runtime behavior

- The console binds to `127.0.0.1:8000` by default. `--host` and `--port` override `PIPE_WORKS_HOST` and `PIPE_WORKS_PORT`; the port must be an integer from 1 through 65535. The default SQLite path is `pipe-works.db` at the project root; `PIPE_WORKS_DB_PATH` overrides it.
- Process definitions are persisted in SQLite. `POST /api/processes` is an upsert keyed by `process_id`; `PUT` updates an existing definition and requires the URL and body IDs to match. Editing a definition does not restart an already running process. The UI exposes delete for all saved processes, while the DELETE API itself does not stop a running process.
- Runtime state is determined with psutil process enumeration. States are limited to `running` and `stopped`; HTTP inspection failures return 503, while WebSocket polling skips the failed update and retries on the next cycle.
- Stop uses `taskkill /PID <pid> /T /F`, so it force-terminates the process tree without waiting for pipeline cleanup.
- The auto-start monitor polls once per second, but tracks only process IDs explicitly started through this Conductor instance. It restarts a tracked process when its saved `auto_start` is true and the process is no longer found. It does not launch all saved auto-start definitions on Conductor startup. Setting auto_start false suppresses restart while false but does not stop a running process or remove its in-memory tracking entry.
- The browser refreshes process state and statistics over separate WebSockets and retries closed sockets after 2 seconds. Statistics are cumulative process-local snapshots sent every second. Logs are retained in memory up to 500 events per process; each browser log view also retains at most 500 rendered lines. No authentication or CSRF protection is implemented; deployment is intended for a trusted local environment.
- In the process editor, choosing `bypass` disables and clears metadata, inference, and postprocess controls. The server also forces these stages off when parsing a bypass definition.

## Current implementation additions

- Process definitions include `log_level`, with supported values `DEBUG`, `INFO`, `WARNING`, `ERROR`, and `CRITICAL`, defaulting to `INFO`. The editor persists the selection and the supervisor forwards it to the pipeline as `--log-level`.
- Process statistics include nullable numeric `average_ms` in addition to the five integer counters. The pipeline provides it for NVIDIA mode as per-frame decode-call-start to encode-call-return average; bypass leaves it null. The UI renders a compact value such as `33.32 ms/F` immediately before the process action buttons; an unavailable value displays `— ms/F`.
- The process card's configured metadata, inference, and postprocess module indicators can open the configured existing Python file through `POST /api/processes/open-module`. Windows uses the default file opener; unsupported platforms return 501.
- The process menu provides edit, delete, logs, and duplicate actions. Duplicate asks for a new process ID, checks for an existing ID before saving, and copies the configuration to a new definition.
