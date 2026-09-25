# 작업 목록: Conductor 콘솔 및 프로세스 관리

`[x]`는 현재 소스 또는 테스트에서 구현이 확인된 항목이다. 테스트 파일이 없는 통합 경로는 완료로 표시하지 않는다.

## 1단계: 서버·저장소 기반

- [x] T001 `tests/conftest.py`에 격리된 임시 DB와 HTTP 테스트 픽스처를 추가한다.
- [x] T002 `src/conductor/cli.py`에서 `Database`, `Supervisor`, `HttpServer`를 생성해 기본 포트 8000으로 서버를 시작한다.
- [x] T003 `src/conductor/repository/database.py`에 프로세스 설정 CRUD, 환경 변수 경로 재정의 및 저장소 루트 기본 DB 경로를 구현한다.
- [x] T004 `tests/unit/test_database.py`에 설정·자동 시작 플래그 저장 및 조회 테스트를 작성한다.

## 2단계: 설정 API와 웹 콘솔

- [x] T005 [P] `tests/integration/test_http_server.py`에 정적 파일과 프로세스 CRUD API 테스트를 작성한다.
- [x] T006 `src/conductor/web/http_server.py`에 HTML·정적 자원 제공과 프로세스 생성·목록·수정·삭제 API를 구현한다.
- [x] T007 `src/conductor/web/http_server.py`에서 요청 파라미터를 파이프라인 CLI 파서로 검증하고 오류 상태를 반환한다.
- [x] T008 `src/conductor/web/static/index.html`에 프로세스 목록, 설정 폼, 동작 확인 및 로그 대화상자 구조를 구성한다.
- [x] T009 `src/conductor/web/static/index.js`에 설정 CRUD 요청, FPS 숫자 변환을 포함한 폼 상태 제어, 목록 렌더링과 오류 표시를 구현한다.
- [x] T010 `src/conductor/web/static/index.css`에 기존 콘솔의 카드·폼·상태 표시 디자인을 구현한다.
- [x] T011 `src/conductor/web/static/index.js`에서 프로세스 로그 대화상자를 실시간 로그 스트림에 연결한다.

## 3단계: Windows 프로세스 관리

- [x] T012 [P] `tests/unit/test_supervisor.py`에 Windows 명령행 식별, 중복 실행, 시작·정지 오류 테스트를 보강한다.
- [x] T013 [P] `tests/integration/test_process_lifecycle.py`에 Conductor 재시작 이후 실행 상태 탐색·정지 시나리오를 추가한다.
- [x] T014 `src/conductor/domain/supervisor.py`에 `process_id`를 포함한 파이프라인 명령 실행을 구현한다.
- [x] T015 `src/conductor/domain/supervisor.py`에 OS 프로세스 명령행 탐색과 정확한 `--process-id` 대조를 구현한다.
- [x] T016 `src/conductor/domain/supervisor.py`에 일치 프로세스 트리의 `taskkill /T /F` 종료를 구현한다.
- [x] T017 `src/conductor/web/http_server.py`에 실행 상태·시작·정지 API를 구현한다.
- [x] T018 상태·시작·정지 API의 Supervisor 호출을 thread pool에서 실행하고, 지연 중에도 다른 API 요청이 처리되는 통합 테스트를 추가한다.

## 4단계: 운영 상태와 복구

- [x] T019 사용자가 시작한 프로세스만 `auto_start` 설정에 따라 비정상 종료 시 복구하고, 설정 해제 시 실행 중 프로세스를 유지한다.
- [x] T020 상태 API를 일괄 조회로 바꾸고 psutil로 Windows 프로세스를 검색해 PowerShell 프로세스 생성을 제거한다.
- [x] T022 파이프라인 로그를 bounded queue와 별도 WebSocket 스레드로 Conductor에 전달하고, 프로세스별 최근 500개 로그와 실시간 로그를 UI 패널에 연결한다.
- [x] T023 `src/conductor/cli.py`에 `--host`·`--port` 및 `PIPE_WORKS_HOST`·`PIPE_WORKS_PORT` 설정을 추가하고 바인딩 실패 메시지를 명확히 한다.
- [x] T024 `specs/002-conductor-console/quickstart.md`에 Windows 시작, DB 경로 변경, API 및 프로세스 제어 확인 절차를 기록한다.
- [x] T025 `src/conductor/web/static/index.js`에서 DB 응답의 `gpu_id`를 편집 폼의 `gpuid`에 복원한다.
- [x] T026 Limit process states in the Supervisor status API and WebSocket to `running` or `stopped`; report OS inspection failures as API errors instead of a third state.
- [x] T027 `tests/unit/test_database.py`와 Supervisor 테스트에 FPS 저장·기존 DB 열 마이그레이션·실행 인자 전달 사례를 추가한다.
- [x] T028 `src/conductor/web/static/index.js`의 GPU ID 편집 복원에 대한 회귀 테스트를 추가한다. (`node tests/js/test_gpu_id_restore.test.cjs`)
- [x] T029 Supervisor가 실제 OS 프로세스 실행 상태를 1초마다 WebSocket으로 UI에 전달하고 카드 상태 표시를 부분 갱신한다.
