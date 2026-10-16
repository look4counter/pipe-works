# RTSPPublish: 압축 패킷 RTSP 송출

구현: `src/pipeworks/embedded/rtsp_publish.py`. 가져오기: `from pipeworks.embedded import RTSPPublish`.

## 생성자와 설정

`RTSPPublish(url, *, reconnect=True, reconnect_interval_ms=3000, transport="tcp", timeout_ms=5000, packet_size=1452)`

| 옵션 | 기본값 | 설정 위치와 의미 |
| --- | --- | --- |
| url | 필수 | 생성자 전용 송출 주소. 자리표시자 치환 없이 그대로 사용합니다. |
| reconnect | True | 생성자 / YAML. 출력 연결·송신 오류 후 재시도 여부 |
| reconnect_interval_ms | 3000 | 생성자 / YAML. 실패 후 다음 연결까지의 대기 밀리초 |
| transport | tcp | 생성자 / YAML. tcp 또는 udp |
| timeout_ms | 5000 | 생성자 / YAML. FFmpeg timeout 옵션으로 전달할 밀리초 |
| packet_size | 1452 | 생성자 / YAML. FFmpeg pkt_size 옵션 |

YAML 섹션은 RTSPPublish이며 YAML 값이 우선합니다. 옵션 삭제 시 최초 생성자 값으로 돌아갑니다. 시간 옵션은 bool을 제외한 0 이상의 유한한 숫자여야 하며 위반 시 ValueError입니다. 잘못된 reconnect·transport와 0 이하 packet_size는 현재 구현에서 오류 로그를 남깁니다.

## 입력과 출력

필수 입력은 `packet`과 `video_stream`입니다. 누락하면 ValueError입니다. 압축 패킷을 송출하는 Sink이며 입력을 소비하고 **출력 컨텍스트를 만들지 않습니다**. 인코딩은 [NvidiaEncode](nvidia_encode.md)가 수행합니다. bitrate·framerate·codec은 이 Step의 설정이 아닙니다.

입력 스트림의 인덱스·코덱·해상도·extradata·time_base가 바뀌면 출력 연결을 다시 만듭니다. 패킷의 time_base가 없으면 입력 스트림, 출력 스트림 순으로 보완하며 유효한 양수 시간 기준이 없으면 ValueError입니다. DTS 누락은 PTS 또는 이전 송신 DTS와 duration으로 보완하고, 이전 DTS 이하이면 시간 기준을 환산해 증가하도록 보정합니다. 이때 기존 PTS도 같은 차이만큼 이동합니다. 시간 보정과 출력 stream 지정은 송신 전용 패킷에 적용하며 입력 패킷은 변경하지 않습니다.

송신마다 독립적인 av.Packet과 FFmpeg 패딩을 갖춘 압축 버퍼를 만들고 압축 데이터를 한 번 복사합니다. 영상 프레임·GPU 버퍼는 복사하지 않습니다. PTS·DTS·duration·time_base·키프레임·손상 표시와 부가 데이터도 독립 복사하므로 동일 입력을 여러 송신 단계에서 사용할 수 있습니다. 단, 사용자 코드가 원본 패킷을 동시에 수정해서는 안 됩니다.

PyAV 공개 API로 보존할 수 없는 is_discard·is_trusted·is_disposable 플래그가 참인 패킷은 ValueError로 거부합니다. 입력 파일 위치 pos와 opaque는 송신에 복사하지 않습니다. 재연결 대기 중 생략하는 입력은 복사하지 않습니다.

## 오류와 종료

연결 또는 mux 실패 시 reconnect=False이면 예외를 전달합니다. True이면 연결을 닫고 재시도 시각을 예약합니다. 대기 중에도 상류 입력을 소비하며 해당 패킷은 버리고 출력하지 않습니다. 실패 패킷을 보관하거나 재송신하지 않습니다. 입력 계약·시간 기준 오류는 재연결로 숨기지 않습니다. 정상 종료·오류·조기 종료 시 출력 연결을 닫습니다.

## 사용 예

```python
from pipeworks.embedded import NvidiaEncode, RTSPPublish

pipeline.step(NvidiaEncode(fps=30))
pipeline.step(RTSPPublish("rtsp://mediamtx:8554/camera"))
```

전체 실행 통계는 [StreamReport](stream_report.md)를 함께 사용합니다. 이 Sink 뒤의 보고자는 입력을 전달받지 않지만 상류 소비 동안 주기 출력을 수행할 수 있습니다.

## 비디오 메타데이터

video_stream에는 불변 VideoStreamInfo를 전달합니다. 원본 수신 스트림 대신 복사한 값으로 출력 스트림을 구성하며 extradata를 보존하고 별도 소프트웨어 인코더를 열지 않습니다. 연결 식별자 connection_id가 바뀌면 코덱·해상도가 같아도 출력 연결을 다시 만듭니다. 사용자 정의 소스는 열린 컨테이너에서 VideoStreamInfo.from_stream을 연결당 한 번 호출해야 합니다.
