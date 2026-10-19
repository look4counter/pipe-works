# RTSPSource: RTSP 압축 패킷 입력

구현: `src/pipeworks/embedded/rtsp_source.py`. 가져오기: `from pipeworks.embedded import RTSPSource`.

## 생성자와 설정

`RTSPSource(url, *, reconnect=True, reconnect_interval_ms=3000, transport="tcp", timeout_ms=5000)`

| 옵션 | 기본값 | 설정 위치와 의미 |
| --- | --- | --- |
| url | 필수 | 생성자 전용 RTSP 주소. 문자열을 그대로 사용하며 자리표시자를 치환하지 않습니다. |
| reconnect | True | 생성자 / YAML. 호환을 위해 유지하는 옵션. 실행 중 일반 오류·입력 종료는 값과 무관하게 재연결 |
| reconnect_interval_ms | 3000 | 생성자 / YAML. 재연결 대기 밀리초 |
| transport | tcp | 생성자 / YAML. tcp 또는 udp |
| timeout_ms | 5000 | 생성자 / YAML. 연결과 읽기에 각각 적용하는 제한 시간(밀리초) |

YAML 섹션은 `RTSPSource`입니다. YAML 값이 생성자 값보다 우선하며 삭제한 옵션은 최초 생성자 값으로 복원됩니다. 시간 옵션은 bool을 제외한 0 이상의 유한한 숫자여야 하며 잘못된 값은 ValueError입니다. reconnect와 transport의 잘못된 값은 현재 구현에서 오류 로그를 남깁니다.

## 입력과 출력

상류 입력 반복자는 사용하지 않습니다. PyAV로 첫 번째 비디오 스트림을 선택하고 크기가 양수인 압축 패킷마다 새 PipelineContext를 출력합니다.

| 출력 필드 | 의미 |
| --- | --- |
| packet | PyAV 압축 패킷. 영상 프레임이 아닙니다. |
| video_stream | 연결당 복사한 불변 비디오 메타데이터 |

프레임이 필요하면 [NvidiaDecode](nvidia_decode.md)를 연결합니다. 재인코딩 없이 [RTSPPublish](rtsp_publish.md)로 패킷을 전달할 수도 있습니다.

## 오류와 종료

비디오 스트림·코덱 정보가 없거나 코덱 이름이 빈 문자열·공백·비문자열이면 연결을 재생성합니다. 너비·높이는 불리언이 아닌 양의 정수여야 합니다. 메타정보 복사·변환 실패, 제공된 시간 기준·평균 프레임률이 0 이하인 경우와 음수 스트림 인덱스도 재생성 대상입니다. 선택 시간 기준·평균 프레임률이 없는 것은 허용합니다.

잘못된 메타정보의 패킷은 후속 단계에 전달하지 않습니다. 수신 실패와 원인 경고를 기록하고 연결을 닫은 후 reconnect_interval_ms만큼 기다려 다시 엽니다. 이 메타정보 복구는 reconnect=False여도 수행하며 중단·취소 신호로 종료할 수 있습니다. 메타정보는 정상 연결당 한 번만 복사해 공유합니다.

일반 연결·수신·입력 처리 오류와 정상 입력 종료는 reconnect 값과 무관하게 연결을 닫고 기존 간격으로 재시도합니다. 명시적인 GPU·하드웨어 오류는 전파합니다. 유효한 코덱 이름이 특정 GPU에서 지원되는지는 디코더의 별도 계약을 따릅니다.

연결은 매 시도 후 닫습니다. 중단 신호와 디코더의 취소 신호를 확인하며 재연결 대기는 취소할 수 있습니다. 이미 진행 중인 연결·읽기 호출은 기존 제한 시간이나 다음 패킷까지 기다릴 수 있습니다.

## 사용 예

```python
from pipeworks.embedded import RTSPSource, NvidiaDecode

pipeline.step(RTSPSource("rtsp://camera/main", timeout_ms=5000))
pipeline.step(NvidiaDecode(gpu_id=0))
```

## 비디오 메타데이터

video_stream은 원본 av.VideoStream이 아닌 불변 VideoStreamInfo입니다. 코덱 이름·해상도·헤더·시간 기준·프레임률을 열린 연결에서 한 번 복사하고 모든 패킷이 공유합니다. 재연결하면 새 connection_id를 만들며 이전 값은 원본 컨테이너 종료 이후에도 유효합니다. packet은 원본 av.Packet으로 유지하며 packet.stream을 후속 메타데이터 접근에 사용하지 않습니다.
