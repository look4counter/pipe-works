# 구현 계획: Conductor 콘솔 및 프로세스 관리

**기능 경로**: `002-conductor-console` | **명세**: [spec.md](spec.md)

## 현재 구성

```text
src/conductor/
├── cli.py                         # Database·Supervisor 생성, host·port 설정과 서버 실행
├── domain/supervisor.py           # Windows 명령행 탐색, 시작·중복 확인·강제 종료
├── repository/database.py         # SQLite 프로세스 정의 CRUD
└── web/
    ├── http_server.py             # FastAPI 정적 파일 및 프로세스 API
    └── static/{index.html,index.css,index.js} # 콘솔 목록·폼·액션

src/pipeline/cli.py                # 시작할 하위 프로세스의 실행 파라미터 계약
```

## 기술 맥락과 결정

- Python 3.11.9, FastAPI, Uvicorn 및 SQLite를 사용한다. 의존성 버전은 `pyproject.toml`에 고정되어 있다.
- 서버는 `conductor.cli`에서 기본 주소 `127.0.0.1:8000`으로 실행한다. `--host`·`--port` CLI 옵션과 `PIPE_WORKS_HOST`·`PIPE_WORKS_PORT` 환경 변수를 지원한다.
- DB 경로는 `PIPE_WORKS_DB_PATH` 환경 변수가 우선이며, 없으면 저장소 루트의 `pipe-works.db`를 사용한다.
- 프로세스 정의의 키는 `process_id`이며, DB에는 PID를 저장하지 않는다. `auto_start`와 모든 파이프라인 파라미터를 저장한다.
- 실행 상태는 psutil로 OS 프로세스를 한 번 순회해 `python.exe`·`pythonw.exe`의 명령행을 확인한다. `-m pipeline.cli --process-id <id>`가 일치해야 한다.
- 정지 시 일치 PID에 `taskkill /PID <pid> /T /F`를 적용한다. 이는 자식 트리를 포함해 강제 종료한다.
- 정적 UI는 설정 CRUD와 시작·정지 API를 호출한다. `/ws/process-status`가 전체 OS 실행 상태를 1초마다 전송하며, UI는 카드 상태 표시만 갱신한다. 편집 시 DB의 `gpu_id`를 폼의 `gpuid`로 복원한다.
- FastAPI 응답은 `HTTPException`으로 오류 상태를 구분하고, 시작 OS 오류는 로그에 기록한 뒤 일반 오류 메시지를 반환한다.

## 데이터 모델

`processes` stores `process_id`, `auto_start`, RTSP URLs/transports, `nvidia`/`bypass` pipe type, GPU ID, optional FPS,
metadata·inference·postprocess 활성화 값과 Python 경로, 추론 간격·프레임 형식을 저장한다. boolean은 SQLite
정수로 기록하고 읽을 때 Python `bool`로 변환한다. 기존 테이블에 `fps` 열이 없으면 초기화 중 추가한다. 이전 legacy CPU 설정은 NVIDIA/GPU 0으로 변환한다. 과거 `runtime_pid` 열이 있으면 값을 비우지만 해당 열이나
PID를 새 실행 상태의 근거로 사용하지 않는다.

## 구성 요소 책임

- `HttpServer`: 요청 필드와 경로의 식별자를 확인하고 파라미터 파서로 설정을 검증한 후 저장소를 호출한다. 상태·시작·정지 요청의 Supervisor 작업은 thread pool로 보내 이벤트 루프를 막지 않는다.
- `Database`: 정의 CRUD만 담당한다. 실행 상태를 DB에 보관하지 않는다.
- `Supervisor`: 파이프라인 명령을 조립하고 Windows OS 프로세스 표에서 정확한 식별자를 찾는다.
- 정적 UI: 폼 검증, 확인 대화상자, API 요청, 목록 렌더링을 담당한다. 로그 패널은 현재 안내 문구만 표시한다.

## 후속 구현 단계

1. 단위·HTTP 통합 테스트로 현행 저장·검증·Windows 프로세스 계약을 고정한다.
2. 프로세스 탐색 실패 상태 처리를 보완한다.
3. 상태 조회를 일괄화하고 psutil을 사용해 PowerShell 실행을 제거한다.
4. `auto_start`의 사용자 시작 프로세스 종료 후 복구 동작을 구현한다.
5. 파이프라인 로그를 전용 스레드 WebSocket으로 수신하고, 프로세스별 최근 로그와 실시간 로그를 UI 패널에 전달한다.
6. 정상 종료가 필요한지 확정한 후 강제 종료 전 정리 절차를 설계한다.

## 운영·보안 제약

- 프로세스 종료는 Windows `taskkill`을 사용한다. 프로세스 열거와 명령행 조회는 psutil을 사용한다.
- Conductor와 대상 프로세스가 조회·종료 가능한 권한으로 실행되어야 한다.
- 로컬 신뢰 환경만 가정하며 인증·원격 노출 제어·CSRF 보호는 설계 범위에 포함되지 않았다.
- 프로세스별 로그와 파이프라인 통계는 WebSocket으로 전달한다. 로그 기록은 Conductor 메모리에 프로세스별 최근 500개까지 보관한다.
