# 검증 안내

저장소 루트에서 .venv/Scripts/python.exe -m unittest discover -s tests -p test_video.py 명령으로 실제 PyAV 파일 회귀 검증을 수행한다.
같은 방식으로 test_rtsp_source.py, test_rtsp_publish.py, test_nvidia_encode.py, test_nvidia_decode.py를 수행하고 전체 discover를 실행한다.
실제 GPU와 RTSP 서버 환경에서는 재인코딩 송출 후 입력 연결을 끊고 재연결하여 SDP 헤더·연속 출력·프로세스 생존을 확인한다. 장비 검증을 로컬 검증 결과로 대체해 보고하지 않는다.

## 실행 결과 (2026-10-16)

- 최종 관련 테스트: 78개 통과. 실제 NVIDIA 인코더의 h264·hevc 복구 후 세대별 메타데이터 공유와 파일 송출·재디코딩 포함.
- 실제 PyAV: h264·hevc 각각 Annex B와 avcC/hvcC 입력을 원본 종료 후 독립 값으로 복원하여 파일 송출·재디코딩 성공. 출력 소프트웨어 인코더가 열리지 않으며 extradata가 유지됨을 확인.
- 입력 성능 계약: 1,000개 패킷에서 from_stream 호출 1회, 동일 메타데이터 객체 1개 확인.
- 전체 회귀: 475개 실행, 통과 470개, 기존 실패 5개(오류 3개·실패 2개). 이후 추가한 필수 값 검증 1개를 포함한 최종 관련 78개도 모두 통과.
- 기존 실패는 test_box_overlay의 예제 단계 구성 1개, test_multiple_stream_example의 누락된 예제 파일 2개, test_remote_example_dependencies의 예제 반환 형식 1개, test_yolo_processing의 예제 구성 1개다. HEAD 소스를 별도 임시 디렉터리에 추출하여 이 5개가 모두 동일하게 실패함을 확인했다.
- 초기 연구에서 PyNvVideoCodec 단독 가져오기는 DLL 오류가 있었으나 기존 테스트의 DLL 디렉터리 설정을 사용한 실제 GPU 테스트는 성공했다.
- 실제 RTSP 서버를 통한 SDP·네트워크 재연결 종단 간 검증은 수행하지 않았다.

## 2026-10-20 생성 검증 제거 확인

기존 가상 환경과 의존성으로 다음 세 명령을 실행한다. 빈 이름·0 및 음수 크기 보존, 독립 복사·불변성, 실제 영상 송출과 RTSP 회귀를 검증한다.

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -p test_video.py -v
.venv/Scripts/python.exe -m unittest discover -s tests -p test_rtsp_source.py -v
.venv/Scripts/python.exe -m unittest discover -s tests -p test_rtsp_publish.py -v
```

검증 결과: 2026-10-20 비디오 5개, RTSP 소스 11개, RTSP 송출 19개로 총 35개 테스트가 모두 통과했다. 변경 전 새 수락 검증의 6가지 입력에서 기존 ValueError를 확인했고 변경 후 모두 통과했다. 실제 RTSP 서버나 GPU 전체 파이프라인 실험은 이번 검증에 포함하지 않았다.

## RTSP 메타정보 복구 검증

기존 가상 환경에서 아래 명령을 실행한다. 비정상 연결의 패킷 차단·닫힘·대기 후 정상 재개, 메타정보 연속 실패, reconnect=False, 중단·취소, 무관한 오류 전파와 기존 공유 계약을 검증한다.

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -p test_rtsp_source.py -v
.venv/Scripts/python.exe -m unittest discover -s tests -p test_video.py -v
.venv/Scripts/python.exe -m unittest discover -s tests -p test_rtsp_publish.py -v
.venv/Scripts/python.exe -m unittest discover -s tests -p test_nvidia_decode.py -v
```

2026-10-20 복구 검증 결과: RTSP 소스 14개, 비디오 5개, RTSP 송출 19개, 디코더 30개로 총 68개 테스트가 모두 통과했다. 소스 테스트에는 21종 비정상 입력을 reconnect=True/False 각각으로 검증하는 42개 하위 사례가 포함된다. 변경 전 복구 테스트 실패를 확인했고 변경 후 모두 통과했다. 디코더 테스트에는 실제 GPU 잠금 버퍼·복구 검증도 포함되며 실제 RTSP 서버를 통한 네트워크 종단 간 검증은 수행하지 않았다.
