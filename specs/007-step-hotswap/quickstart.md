# 검증 안내: Step 핫스왑

1. `python -m unittest discover -s tests -p test_hotswap.py`를 실행한다.
2. 실행 중인 모의 Step 파일의 처리 로직을 바꾸고, 구버전의 잔여 출력 다음부터 신버전의 출력이 나오는지 확인한다.
3. 구문 오류를 저장한 뒤에도 이전 구현의 출력이 계속되는지 확인한다.
4. 소스 Step 변경 후 하류 Step의 상태가 새 구간에서 다시 시작하고 경계 입력이 한 번만 처리되는지 확인한다.
5. `python -m unittest discover -s tests`로 기존 설정·RTSP 계약이 유지되는지 확인한다.

실제 NVIDIA 디코딩·인코딩과 RTSP 서버 송출은 PyNvVideoCodec과 GPU, RTSP 서버가 있는 환경에서 별도로 검증한다.
# 추가 검증: 별도 프로세스의 사용자 Step

1. `01_single_stream_rtsp_style.py`와 같이 메인 파일이 같은 디렉터리의 `step` 패키지를 가져오는 구조를 준비한다.
2. 사용자 Step을 포함한 파이프라인을 별도 프로세스에서 실행한다.
3. 메인 파일의 사용자 Step과 `step` 패키지 파일을 차례로 수정한다.
4. 각 변경 이후 다음 처리 경계부터 새 동작이 나타나고, 파일 오류가 나면 이전 동작이 이어지는지 확인한다.
