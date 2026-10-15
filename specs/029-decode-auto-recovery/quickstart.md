# 검증 안내

저장소 루트에서 다음 명령을 실행한다.

~~~powershell
.venv/Scripts/python.exe -m unittest discover -s tests -p test_nvidia_decode.py
.venv/Scripts/python.exe -m unittest discover -s tests -p test_frame_release.py
.venv/Scripts/python.exe -m unittest discover -s tests -p test_rtsp_source.py
.venv/Scripts/python.exe -m unittest discover -s tests -p test_pipeline_routing.py
~~~

디코딩 오류, 연속 재생성 실패, 다음 키프레임 재개, 스트림 교체, 종료 및 이전 잠금 프레임 유지가 통과해야 한다. CUDA가 있으면 실제 잠금 프레임 복구 시험도 실행한다.

운영 확인: 카메라 재연결이나 손상 패킷 이후 복구 경고가 나오고 다음 정상 키프레임부터 출력 재개 기록이 나오는지 확인한다. 복구 시간은 키프레임 주기와 영상 헤더 전송에 의존한다.

## 검증 결과 (2026-10-15)

디코더 28개, 프레임 해제 6개, RTSP 입력 9개, 실행 경로 5개, 기본 설정 11개, 처리 경계 3개로 총 62개 시험을 통과했다. 디코더 시험에는 실제 CUDA 디코딩 및 복구 중 Tensor/DLPack 별칭 수명 검증이 포함된다. 변경 Python 파일 2개의 구문 검사와 git diff --check도 통과했다. Ruff는 실행 환경에 설치되어 있지 않아 실행하지 못했다. 실제 카메라 장애 현장 재현은 수행하지 않았다.
