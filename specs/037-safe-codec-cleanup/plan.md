# 구현 계획: 코덱 정리와 송신 독립성

## 기술 맥락 및 헌법 검토

Python 3.11.9, PyAV 18.1.0, 기존 PyNvVideoCodec·torch를 유지한다. 새 의존성·컴파일 확장은 없다. 헌법은 미작성 템플릿이므로 규범 검사는 생략하고 한글 문서와 전체 speckit 절차를 준수한다.

## 설계와 수행 순서

1. nvidia_decode.py의 _DecoderBuffers.reap을 인덱스 기반 처리로 바꾸어 성공한 반환은 즉시 retired에서 삭제한다. 미완료 이벤트는 건너뛰고 실패한 항목과 이후 대기는 남긴다.
2. 버퍼 풀에 _cleanup_failed를 기록한다. 실패 후 close·retire·reap은 네이티브 반환을 재시도하지 않고 available·acquire는 실패 풀 재사용을 거부한다. 닫힌 풀의 외부 참조 반환도 같은 경로를 사용한다.
3. NvidiaDecode.reset과 NvidiaEncode.release에 실행별 정리 실패 상태를 두고 최초 실패를 다시 덮어쓰지 않는다. 디코더 풀 실패 시 최종 reset도 추가 GPU 작업을 하지 않는다. 정상 해제 순서는 유지한다.
4. rtsp_publish.py에 송신용 패킷 복사 도우미를 둔다. av.Packet(size)로 FFmpeg 패딩을 갖춘 독립 압축 버퍼를 만들고 update(source)로 한 번 복사한다. PTS·DTS·duration·time_base·키프레임·손상 표시와 side data를 복사한다. 입력 파일 pos와 opaque는 송신에 사용하지 않는다.
5. 읽기 전용 discard·trusted·disposable 플래그가 있는 경우 명시적 ValueError로 거부한다. 필수 시간 검사와 패킷 복사는 네트워크 재시도 예외 처리 밖에서 수행한다. 출력 stream과 시간 보정은 복제에만 적용한다.
6. tests/test_nvidia_decode.py, test_nvidia_encode.py, test_rtsp_publish.py 및 새 tests/test_codec_cleanup.py에서 부분 실패·동기화 실패·후속 정리·병렬 송신과 실제 파일 mux를 검증한다.
7. 디코더·인코더·송신 문서와 새 기능의 검증 안내를 갱신한다.

## 검증과 위험

사용자 지시대로 버퍼 반환 → 정리 실패 → 송신 독립성 순서로 진행한다. 송신 패킷은 실제 av.Packet으로 검사하고 두 출력의 동시 진입을 장벽으로 고정한다. 실제 H.264·HEVC 파일 mux·재디코딩과 기존 GPU 수명·복구 검증을 수행한다.
치명적 GPU 장애를 실제로 발생시키지 않고 오류를 주입한다. 오류를 숨겨 정상 진행하는 검증은 추가하지 않는다. 압축 패킷 복사 비용과 일부 플래그의 명시적 거부를 문서화한다.
