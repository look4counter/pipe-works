# 검증 안내

저장소 루트에서 .venv/Scripts/python.exe -X utf8 -m unittest discover -s tests -p test_nvidia_encode.py 를 실행한다. GPU가 있으면 새 인코더 세션의 출력만 독립 디코딩하는 시험도 실행된다.

관련 회귀 시험은 test_nvidia_decode.py, test_rtsp_publish.py, test_report.py, test_step_config_defaults.py, test_frame_release.py, test_processing_boundary.py를 실행한다. 변경 Python 파일 구문 검사와 git diff --check도 수행한다.

운영 환경에서는 일시 인코딩 오류 후 경고와 출력 재개 기록이 나오고 송출 영상이 정상 진행되는지 확인한다. 실제 네트워크 카메라 송출 호환성은 운영 환경에서 별도 확인한다.

## 검증 결과 (2026-10-15)

인코더 14개, 디코더 28개, 송출 14개, 통계 21개, 기본 설정 11개, 프레임 해제 6개, 처리 경계 3개로 총 97개 시험을 통과했다. 인코더 GPU 시험은 H.264와 HEVC 두 코덱 모두 오류 주입 후 재생성된 세션의 패킷만 새 디코더에 전달하여 25개 프레임과 첫 키프레임을 확인했다. PTS/DTS 연속성, 1초 재시도 경계, 지원 불가·입력 소스·후속 오류 분리 및 종료 정리도 통과했다. Python 파일 2개의 구문 검사와 git diff --check를 통과했다. 실제 RTSP 서버·카메라 송출 현장 시험은 수행하지 않았다.
