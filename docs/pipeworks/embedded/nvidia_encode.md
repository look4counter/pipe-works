# NvidiaEncode: 하드웨어 비디오 인코딩

**파일 위치:** `src/pipeworks/embedded/nvidia_encode.py`

NVIDIA GPU에서 디코딩된 프레임을 압축 패킷으로 변환합니다. 입력에는 `frame`, `video_stream`, `cuda_stream`, `pixel_format`이 필요하며, 출력은 `packet`과 `video_stream`이 있는 새 `PipelineContext`입니다. `RTSPPublish`가 이 패킷을 송출합니다.

## 사용법

```python
from pathlib import Path
from pipeworks import Pipeline
from pipeworks.embedded import RTSPSource, NvidiaDecode, NvidiaEncode, RTSPPublish

pipeline = Pipeline("gpu-encode", config=Path("config.yaml"))
pipeline.step(RTSPSource("rtsp://camera/main"))
pipeline.step(NvidiaDecode())
pipeline.step(NvidiaEncode(gpu_id=0, fps=30))
pipeline.step(RTSPPublish("rtsp://mediamtx:8554/output"))
pipeline.run()
```

## 설정

```yaml
NvidiaEncode:
  gpu_id: 0
  fps: 30
```

YAML 값이 생성자보다 우선하며 삭제하면 최초 생성자 값으로 돌아갑니다. GPU 기본값은 0, FPS 기본값은 30입니다. FPS는 양수여야 합니다. 현재 시간 기준 생성은 정수 FPS를 사용해야 하며 `30.0`·`29.97` 같은 실수는 처리 시작 시 오류가 발생합니다.

코덱·해상도·픽셀 형식은 첫 입력에서 읽습니다. 인코더의 FPS·GOP·IDR 간격은 설정된 FPS를 사용합니다. 현재 구성에서 비트레이트와 코덱을 별도 옵션으로 지정하지 않습니다. 입력 도중 형식이 바뀌어도 인코더를 자동 재생성하지 않습니다.

## 패킷과 종료

빈 압축 결과는 건너뛰고, 여러 결과는 순서대로 개별 PyAV 패킷으로 전달합니다. 각 패킷의 PTS·DTS는 0부터 증가하며 시간 기준은 FPS의 역수, 지속 시간은 1입니다. 정상 입력 종료 시 `EndEncode()`의 잔여 결과에도 같은 계약을 적용합니다.

새 컨텍스트에 감지 결과 등 임의 입력 속성을 자동으로 복사하지 않습니다. 결과를 소비하는 단계는 인코딩 앞에 둡니다. 실제 인코딩 패킷과 원본 스트림 템플릿의 RTSP 송출 호환성은 실행 환경에서 확인해야 합니다.

관련 문서: [디코딩](nvidia_decode.md), [패킷 송출](rtsp_publish.md), [파이프라인](../pipeline.md)
