# 빠른 검증: Conductor 콘솔 및 프로세스 관리

## 현재 구현 확인

1. Python 3.11.9 환경에서 프로젝트 의존성을 설치하고 저장소 루트에서 `conductor`를 실행한다. 기본 주소는 `127.0.0.1:8000`이며 `conductor --host 0.0.0.0 --port 8080` 또는 `PIPE_WORKS_HOST`·`PIPE_WORKS_PORT`로 변경할 수 있다.
2. 브라우저에서 `http://127.0.0.1:8000/`을 열고 콘솔 HTML, CSS, JavaScript가 로드되는지 확인한다.
3. 콘솔에서 유효한 RTSP 파라미터로 프로세스 정의를 추가한다. FPS·INTERVAL FRAME을 비우면 각각 30·3으로 저장되는 것을 확인한다.
4. 편집 시 GPU ID가 복원되는지 확인하고, 삭제 API·유효하지 않은 파라미터의 422 응답·존재하지 않는 ID의 404 응답을 확인한다.
5. 테스트용 파이프라인 실행 정의로 시작·상태·정지 동작을 확인한다. 정지는 Windows `taskkill /T /F`를 사용하므로 테스트 프로세스만 지정한다. 사용자가 시작한 프로세스는 `auto_start=true`일 때 Conductor 실행 중 종료되면 다시 시작된다. `auto_start`를 해제하면 실행 중인 프로세스는 유지되고 자동 재시작만 비활성화된다.
6. `PIPE_WORKS_DB_PATH`를 임시 DB 경로로 지정해 기본 경로 대신 해당 파일이 사용되는지 확인한다.

## 현재 알려진 제약

- `conductor.cli` 기본 주소·포트는 `127.0.0.1:8000`이며 `--host`·`--port` 또는 `PIPE_WORKS_HOST`·`PIPE_WORKS_PORT`로 변경할 수 있다.
- 프로세스 상태 확인은 psutil로 OS 프로세스와 명령행을 조회한다.
- Conductor 재시작을 넘어 사용자가 시작한 프로세스의 자동 재시작 추적을 복원하지는 않는다. 프레임 카운터와 프로세스 로그는 WebSocket으로 UI에 전달된다.
- `pipe_type` supports `nvidia` and `bypass`. Bypass automatically disables metadata, inference, and postprocess; GPU ID is relevant only to NVIDIA.
- FPS는 저장·조회·하위 프로세스 인자 전달·NVIDIA 인코더 설정까지 지원한다. 입력 프레임의 실제 전송률 조정은 구현되어 있지 않다.
