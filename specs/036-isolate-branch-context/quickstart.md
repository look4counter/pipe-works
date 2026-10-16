# 검증 안내

저장소 루트에서 .venv/Scripts/python.exe -m unittest discover -s tests -p test_tap_skip_if_busy.py 명령으로 분기 격리 검증을 실행한다.
같은 방식으로 test_hotswap.py, test_async.py, test_frame_release.py, test_report.py 및 test_central_process.py를 실행하여 기존 핫스왑·프레임 수명·배경 로그 계약을 확인한다.
실제 파일 변경을 사용하는 검증은 임시 디렉터리를 사용하며 프로젝트 소스 파일은 수정하지 않는다.

## 실행 결과 (2026-10-16)

- 수정 전 새 검증 6개 중 4개 실패: 실제 배경 코드 교체가 주 경로 누적을 1, 2로 초기화하고, 속성 사전이 공유되며, 원본에서 삭제한 디코더 소유자를 배경 경로가 유지하지 못하는 문제를 확인했다.
- 수정 후 새 검증 6개 모두 통과. 배경 파일 교체 후 주 경로 누적은 1, 3으로 유지된다. 최상위 속성과 epoch는 양방향 격리되며 공통 상류 epoch는 유지된다.
- test_tap_skip_if_busy.py·test_hotswap.py·test_async.py·test_frame_release.py·test_report.py 합계 104개 통과(7.306초).
- test_nvidia_decode.py·test_central_process.py·test_remote_logging.py 합계 71개 통과(42.174초). 실제 GPU 디코더·DLPack 별칭 수명과 배경 로그 전달을 포함한다.
- 관련 검증 총 175개 통과. 영상·패킷·CUDA 스트림·메타데이터·디코더 소유자의 참조 동일성을 확인했고 깊은 복사와 버퍼 clone은 추가하지 않았다.
- git diff --check 통과. 중첩 데이터는 공유하므로 배경 작업이 읽기 전용으로 사용해야 한다. 실제 RTSP 서버를 사용하는 별도 종단 간 실험은 수행하지 않았다.
