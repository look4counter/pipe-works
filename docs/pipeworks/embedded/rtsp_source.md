# RTSPSource: RTSP 압축 패킷 입력

구현: `src/pipeworks/embedded/rtsp_source.py`. 가져오기: `from pipeworks.embedded import RTSPSource`.

## 생성자와 설정

`RTSPSource(url, *, reconnect=True, reconnect_interval_ms=3000, transport="tcp", timeout_ms=5000)`

| 옵션 | 기본값 | 설정 위치와 의미 |
| --- | --- | --- |
| url | 필수 | 생성자 전용 RTSP 주소. 문자열을 그대로 사용하며 자리표시자를 치환하지 않습니다. |
| reconnect | True | 생성자 / YAML. 연결·수신 실패와 정상 입력 종료 후 재연결 여부 |
| reconnect_interval_ms | 3000 | 생성자 / YAML. 재연결 대기 밀리초 |
| transport | tcp | 생성자 / YAML. tcp 또는 udp |
| timeout_ms | 5000 | 생성자 / YAML. 연결과 읽기에 각각 적용하는 제한 시간(밀리초) |

YAML 섹션은 `RTSPSource`입니다. YAML 값이 생성자 값보다 우선하며 삭제한 옵션은 최초 생성자 값으로 복원됩니다. 시간 옵션은 bool을 제외한 0 이상의 유한한 숫자여야 하며 잘못된 값은 ValueError입니다. reconnect와 transport의 잘못된 값은 현재 구현에서 오류 로그를 남깁니다.

## 입력과 출력

상류 입력 반복자는 사용하지 않습니다. PyAV로 첫 번째 비디오 스트림을 선택하고 크기가 양수인 압축 패킷마다 새 PipelineContext를 출력합니다.

| 출력 필드 | 의미 |
| --- | --- |
| packet | PyAV 압축 패킷. 영상 프레임이 아닙니다. |
| video_stream | 선택한 입력 비디오 스트림 |

프레임이 필요하면 [NvidiaDecode](nvidia_decode.md)를 연결합니다. 재인코딩 없이 [RTSPPublish](rtsp_publish.md)로 패킷을 전달할 수도 있습니다.

## 오류와 종료

비디오 스트림이 없으면 RuntimeError입니다. FFmpeg 연결·수신 오류는 reconnect=True이면 기록 후 재시도하고 False이면 RuntimeError로 전달합니다. 정상 입력 종료도 False이면 RuntimeError입니다. 다른 예외를 모두 재시도하는 것은 아닙니다.

연결은 매 시도 후 닫습니다. 중단 신호와 디코더의 취소 신호를 확인하며 재연결 대기는 취소할 수 있습니다. 이미 진행 중인 연결·읽기 호출은 기존 제한 시간이나 다음 패킷까지 기다릴 수 있습니다.

## 사용 예

```python
from pipeworks.embedded import RTSPSource, NvidiaDecode

pipeline.step(RTSPSource("rtsp://camera/main", timeout_ms=5000))
pipeline.step(NvidiaDecode(gpu_id=0))
```
