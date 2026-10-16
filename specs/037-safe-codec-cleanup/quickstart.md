# 검증 안내

저장소 루트에서 .venv/Scripts/python.exe -m unittest discover -s tests -p test_codec_cleanup.py 명령으로 오류 주입 검증을 수행한다.
같은 방식으로 test_nvidia_decode.py, test_nvidia_encode.py, test_rtsp_publish.py, test_video.py를 실행한다. 연계 핫스왑·비동기·프레임 수명 검증도 수행한다.
동시 송신은 스레드 장벽으로 겹치게 하고 실제 H.264·HEVC 압축 패킷을 파일에 mux하여 재디코딩한다. 실제 치명적 GPU 장애나 RTSP 서버 네트워크 장애를 재현했다고 보고하지 않는다.

## 실행 결과 (2026-10-16)

- 1번 수정 전 부분 반환 실패 검증 3개가 실패했으며 성공 포인터가 retired에 남는 문제를 재현했다. 즉시 제거 적용 후 모두 통과했다.
- 2번 정리 재진입 검증에서 최초 동기화 오류가 두 번째 오류로 바뀌고 실패한 반환을 다시 호출하는 문제를 재현했다. 실패 상태를 적용한 후 코덱 정리·기존 디코더·인코더 검증 57개를 통과했다.
- 3번 기존 송신에서는 원본 DTS·time_base·stream·데이터가 바뀌고 동시 송신에서 다른 출력 스트림이 연결되는 문제를 재현했다. 독립 패킷 적용 후 송신 검증 19개를 통과했다.
- 실제 H.264·HEVC 압축 패킷을 두 스레드에서 별도 파일로 송출하고 각각 재디코딩했다. 원본 내용·PTS·DTS·time_base·stream 불변을 확인했다.
- 전체 unittest 499개 실행(146.237초): 494개 통과, 기존 예제 실패 5개(오류 3개·실패 2개). 실제 GPU 코덱·DLPack 수명·복구 및 비동기·핫스왑 검증을 포함한다.
- 실패 5개는 test_box_overlay 예제 구성, test_multiple_stream_example 누락 파일 2개, test_remote_example_dependencies 반환 형식, test_yolo_processing 예제 구성이다. HEAD를 별도 임시 디렉터리에 추출하여 같은 5개가 모두 동일하게 실패함을 확인했다.
- git diff --check 통과. 실제 치명적 GPU 장애와 실제 RTSP 서버 네트워크 종단 간 실험은 수행하지 않았다.
- 비용 및 제한: 각 실제 송신에 압축 패킷 데이터 복사 1회가 추가된다. 영상·GPU 버퍼는 복사하지 않는다. is_discard·is_trusted·is_disposable가 참이면 공개 API로 플래그를 보존할 수 없어 명시적 ValueError를 전달한다.
