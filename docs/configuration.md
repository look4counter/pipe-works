# 외부 YAML 설정 Reference

Pipe Works의 Python DSL은 Pipeline의 **What**을 표현하고 YAML은 실행 방식의
**How**를 조정한다. 따라서 YAML에 RTSP 주소, 모델 경로, Action URL, 출력
주소를 옮기지 않는다. 그런 값은 `pipeline.py`를 열었을 때 바로 보여야 한다.

```python
pipeline = (
    Pipeline("cobble")
    .source(RTSPSource("rtsp://camera/main"))
    .inference(YoloInference("models/cobble.engine"))
    .output(RTSPPublisher("rtsp://mediamtx/cobble"))
)
```

```yaml
YoloInference:
  confidence: 0.7
  device: cuda:0
  fp16: true
```

## 읽기 규칙

설정은 `RuntimeConfig.defaults()`의 기본값에서 시작하고 YAML 값으로 덮어쓴다.
YAML에 없는 값은 기본값을 사용하므로 최소 override만 작성하면 된다.

적용 우선순위는 다음과 같다.

1. SDK 기본값
2. 섹션 이름이 `RTSPSource`, `YoloInference`처럼 컴포넌트 계약과 일치하는 값
3. 실제 클래스 이름 또는 컴포넌트 `name`으로 작성한 더 구체적인 값

예를 들어 `GStreamerRTSPSource`는 `RTSPSource`의 공통 reconnect/timeout 설정을
사용하고, 별도의 `GStreamerRTSPSource` 섹션이 있으면 그 값이 더 구체적으로
적용된다. 알 수 없는 섹션은 보존되지만 SDK 기본 Worker가 사용하지 않을 수
있으므로, 오탈자는 `Pipeline.compile().config_summary`와 로그로 확인한다.

## Pipeline

Pipeline 사이의 큐와 오류 격리를 조정한다.

| 키 | 자료형 | 기본값 | 설명 |
| --- | --- | ---: | --- |
| `queue_size` | 정수 | `8` | 단순 실행 경로의 Frame 큐 최대 크기 |
| `drop_policy` | 문자열 | `latest` | 큐 초과 시 정책: `latest`, `drop_oldest`, `block` |
| `worker_queue_size` | 정수 | `64` | Worker 단계 사이 Context 큐 최대 크기 |
| `worker_drop_policy` | 문자열 | `latest` | Worker 큐 초과 시 최신성 우선 정책 |
| `isolate_errors` | 불리언 | `false` | `true`면 Context 오류를 기록하고 다른 Frame 계속 처리 |

실시간 영상은 오래된 Frame을 쌓기보다 최신 Frame을 처리하는 것이 일반적이므로
기본값은 `latest`다. 정확한 모든 Frame 처리가 필요한 배치성 작업이라면 drop 정책과
큐 포화 시 처리량을 별도로 검증한다.

## RTSPSource

`RTSPSource`와 `GStreamerRTSPSource`에 적용되는 입력 복구 정책이다.

| 키 | 자료형 | 기본값 | 설명 |
| --- | --- | ---: | --- |
| `reconnect` | 불리언 | `true` | 입력 오류 뒤 재연결 시도 여부 |
| `reconnect_attempts` | 정수 | `3` | 한 번의 입력 오류에 대한 최대 시도 횟수 |
| `reconnect_interval` | 숫자(초) | `3` | 재연결 사이 대기 시간 |
| `timeout` | 숫자(초) | `10` | Source adapter가 사용하는 연결/읽기 제한 시간 |

실제 GStreamer 파이프라인의 네트워크 timeout 지원 여부는 배포 adapter 구현에
따라 다를 수 있다. 장비가 끊겼다 복구되는 테스트를 반드시 수행한다.

## Realtime freshness 정책

이 섹션은 원본과 합성 영상의 시간 차이를 제한한다. SDK Worker Runtime은
`max_frame_age_ms`를 기준으로 오래된 Frame을 단계 진입 전에 폐기하고,
output latency max/avg/p95를 metrics로 기록한다. 실제 encoded MediaMTX
publish까지의 종단 지연은 배포 환경에서 별도로 검증한다.

| 키 | 자료형 | 설계 기본값 | 설명 |
| --- | --- | ---: | --- |
| `max_end_to_end_latency_ms` | 정수 | `1000` | 입력 수신부터 출력 publish까지 허용할 최대 지연 |
| `max_frame_age_ms` | 정수 | `800` | 추론/출력 단계에 진입할 수 있는 최대 Frame age |
| `drop_policy` | 문자열 | `latest` | 지연 시 최신 Frame 우선 정책 |
| `drop_expired_frames` | 불리언 | `true` | freshness budget 초과 Frame 폐기 여부 |
| `output_latency_action` | 문자열 | `drop` | 출력 직전 초과 시 `drop` 또는 운영 오류 처리 |

목표 설정 예시:

```yaml
Realtime:
  max_end_to_end_latency_ms: 1000
  max_frame_age_ms: 800
  drop_policy: latest
  drop_expired_frames: true
  output_latency_action: drop
```

이 정책은 모든 Frame을 보존하는 분석 시스템과 trade-off가 있다. 실시간 화면이
오래된 영상을 보여주지 않아야 하는 Pipeline에서는 지연된 Frame을 버리는 것이
의도된 정상 동작이다. 관련 acceptance criteria는
`docs/adr/006-freshness-over-completeness.md`를 따른다.

## BatchInference

Multi-stream Batch 수집 정책이다. Pipeline 코드의 `.batch_inference(...)`가
Batch 의미를 결정하고, YAML은 기다리는 시간과 포화 정책을 조정한다.

| 키 | 자료형 | 기본값 | 설명 |
| --- | --- | ---: | --- |
| `max_batch_size` | 정수 | `16` | Batch에 포함할 최대 Context 수 |
| `max_wait_ms` | 정수 | `20` | Batch가 덜 찼을 때 기다릴 최대 시간(밀리초) |
| `drop_policy` | 문자열 | `latest` | Batch 대기열이 포화될 때 정책 |

9채널 예제는 `max_batch_size: 9`를 사용한다. 실제 GPU 처리량과 카메라 FPS에
맞춰 조정하되, batch 결과 순서와 `stream_id` 매핑을 함께 검증한다.

## YoloInference

YOLO 추론 방식이다. 모델 파일 경로 자체는 Python의 `YoloInference(...)`에 둔다.

| 키 | 자료형 | 기본값 | 설명 |
| --- | --- | ---: | --- |
| `confidence` | 숫자 | `0.5` | Detection confidence 하한 |
| `device` | 문자열 | `cpu` | `cpu`, `cuda:0` 등 실행 장치 |
| `fp16` | 불리언 | `false` | GPU half precision 사용 여부 |
| `inference_retry` | 정수 | `0` | 일시적 추론 오류 재시도 횟수 |

GPU 설정은 CUDA, 드라이버, 모델 지원 여부가 맞아야 한다. CPU에서 먼저 DSL과
결과 매핑을 확인한 뒤 GPU 설정을 켠다.

## TensorRTInference

TensorRT도 동일하게 `inference_retry`를 사용한다. CUDA buffer binding과 plugin
초기화는 배포마다 다르므로 YAML이 TensorRT Session을 대신 만들지 않는다.
Python에서 `TensorRTSessionFactory(loader=...)`를 주입하고, YAML은 retry 같은
실행 정책만 둔다.

## Action

HTTP, SVG, MQ 등 외부 부수 효과의 실행 정책이다.

| 키 | 자료형 | 기본값 | 설명 |
| --- | --- | ---: | --- |
| `timeout` | 숫자(초) | `3` | 외부 요청 제한 시간 |
| `retry` | 정수 | `0` | 실패한 Action 재시도 횟수 |
| `max_workers` | 정수 | `4` | 비동기 Action worker 수 |
| `max_pending` | 정수 | `64` | 대기 가능한 Action 최대 수 |

Action이 느려도 영상 출력 경로가 막히지 않도록 bounded queue를 사용한다.
`max_pending`이 작으면 Action drop 메트릭이 증가할 수 있으므로 `/metrics`에서
`actions_dropped`와 오류를 함께 확인한다.

## RTSPPublisher

RTSP/MediaMTX 출력 adapter의 인코딩 튜닝값이다. URL은 Python 코드에 둔다.

| 키 | 자료형 | 기본값 | 설명 |
| --- | --- | ---: | --- |
| `codec` | 문자열 | `h264` | 출력 codec |
| `fps` | 숫자 | `25` | 목표 출력 FPS |
| `bitrate` | 문자열 | `4M` | 인코더 bitrate |

Multi-stream 출력에서는 `MediaMTXPublisher("rtsp://mediamtx/{stream_id}")`처럼
`{stream_id}` 템플릿을 사용할 수 있다. SDK가 Context의 Stream ID로 URL을
해석한 뒤 publisher callback/adapter에 전달한다.

현재 SDK의 MediaMTX adapter는 출력 경계 계약을 제공하며, 실제 encoding/RTSP
publish는 배포 환경 adapter가 담당한다. 이 값이 실제 GStreamer encoder에 전달되는
지점은 운영 adapter 통합 테스트에서 확인한다.

## 전체 예시

```yaml
Pipeline:
  worker_queue_size: 128
  worker_drop_policy: latest
  isolate_errors: true

RTSPSource:
  reconnect: true
  reconnect_attempts: 5
  reconnect_interval: 2
  timeout: 10

BatchInference:
  max_batch_size: 9
  max_wait_ms: 20
  drop_policy: latest

YoloInference:
  confidence: 0.7
  device: cuda:0
  fp16: true
  inference_retry: 1

Action:
  timeout: 3
  retry: 3
  max_workers: 4
  max_pending: 128

RTSPPublisher:
  codec: h264
  fps: 25
  bitrate: 4M
```

## 확인 방법

```powershell
$env:PYTHONPATH='src'
python examples/05_local_synthetic_config.py
python -m pytest -q
python -m pipeworks.cli --check
```

운영 배포에서는 YAML에 Secret, 비밀번호, 토큰을 직접 넣지 않는다. 환경 변수,
Kubernetes Secret, Docker Secret 등 배포 시스템이 제공하는 안전한 주입 방식을
사용하고, YAML에는 queue/retry/device 같은 비밀이 아닌 튜닝값만 둔다.
