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

코덱·해상도·픽셀 형식은 첫 입력에서 읽습니다. 인코더의 FPS·GOP·IDR 간격은 설정된 FPS를 사용합니다. 현재 구성에서 비트레이트와 코덱을 별도 옵션으로 지정하지 않습니다. 입력 스트림 객체나 코덱·해상도·픽셀 형식·CUDA 스트림 핸들이 바뀌면 인코더를 자동 재생성합니다. 기존 정상 인코더의 잔여 출력은 이전 스트림 정보로 전달한 뒤 교체합니다.

## 자동 복구

별도 설정 없이 복구 가능한 인코더 생성 및 프레임 인코딩 오류를 처리합니다. 실패한 프레임과 인코더는 버리고, 실패 후 최소 1초가 지난 뒤 도착하는 최신 프레임에서 인코더를 다시 생성합니다. 연속 실패에도 횟수 제한 없이 같은 방식으로 재시도합니다. 대기 중 입력 프레임은 저장하지 않고 소비하여 버리므로 일시적인 영상 정지와 프레임 누락이 있을 수 있습니다.

실패한 인코더에 EndEncode를 다시 호출하지 않습니다. 오류 복구·입력 교체·종료 시 기존 CUDA 스트림의 작업 완료를 기다린 뒤 인코더, 마지막 제출 입력, 스트림 순서로 참조를 해제합니다. 정상 프레임마다 CPU 동기화를 추가하지 않습니다. 복구용 내부 예외는 원인 문자열만 보유하여 이전 호출의 traceback이 코덱과 프레임 수명을 연장하지 않게 합니다. 입력 종료 시 복구 가능한 EndEncode 오류가 발생하면 경고를 기록하고 잔여 출력을 버립니다. 중지 요청 시에는 재시도나 종료 인코딩을 수행하지 않습니다.

H.264/HEVC는 IDR마다 필요한 영상 헤더를 반복하도록 설정합니다. 재생성한 세션은 재생 가능한 시작 프레임과 헤더를 제공하며, 패킷 PTS/DTS는 복구나 입력 변경 때문에 0으로 돌아가지 않습니다. 실행 중에는 process 시작의 FPS와 시간 기준을 유지합니다. 타임스탬프는 출력 패킷 수 기준이며 버린 프레임의 실제 경과 시간을 반영하지 않습니다.

오류 원인은 경고 로그로, 실제 압축 패킷 출력 재개는 정보 로그로 기록합니다. 설정·지원하지 않는 기능·입력 소스·후속 처리 오류와 GPU 동기화 실패는 자동 복구로 숨기지 않습니다. Python 예외로 잡히지 않는 네이티브 프로세스 충돌이나 복구 불가능한 GPU 장애는 복구를 보장하지 않습니다.

## 패킷과 종료

빈 압축 결과는 건너뛰고, 여러 결과는 순서대로 개별 PyAV 패킷으로 전달합니다. 각 패킷의 PTS·DTS는 0부터 증가하며 시간 기준은 FPS의 역수, 지속 시간은 1입니다. 정상 입력 종료 시 `EndEncode()`의 잔여 결과에도 같은 계약을 적용합니다.

새 컨텍스트에 감지 결과 등 임의 입력 속성을 자동으로 복사하지 않습니다. 결과를 소비하는 단계는 인코딩 앞에 둡니다. 실제 인코딩 패킷과 원본 스트림 템플릿의 RTSP 송출 호환성은 실행 환경에서 확인해야 합니다.

관련 문서: [디코딩](nvidia_decode.md), [패킷 송출](rtsp_publish.md), [파이프라인](../pipeline.md)

## 공개 API와 컨텍스트 계약

구현: `src/pipeworks/embedded/nvidia_encode.py`. 가져오기는 `from pipeworks.embedded import NvidiaEncode`이며 생성자는 `NvidiaEncode(*, gpu_id=0, fps=30)`입니다. 두 옵션은 NvidiaEncode YAML 섹션으로 덮어쓰고 삭제 시 최초 생성자 값으로 돌아갑니다. fps가 0 이하이면 ValueError입니다. 패킷 시간 기준은 Fraction(1, fps)로 계산하므로 현재 구현에서는 양의 정수 fps를 사용합니다.

필수 입력은 frame·pixel_format·video_stream·cuda_stream입니다. processing_started_at은 프레임 처리 시간 기록에 사용하는 선택 필드입니다. 첫 입력의 스트림 코덱·너비·높이와 픽셀 형식으로 인코더를 만들고 B프레임을 끕니다. codec·bitrate·framerate는 공개 설정 키가 아닙니다.

출력은 packet과 video_stream만 가진 새 PipelineContext입니다. 원본 frame이나 사용자 속성을 복사하지 않습니다. 패킷 PTS/DTS는 0부터 증가하며 duration=1, time_base=1/fps입니다. 입력 하나에서 패킷이 없거나 여러 개일 수 있고 정상 입력 종료 시 EndEncode의 잔여 패킷도 출력합니다. 복구 가능한 네이티브 인코더 오류에는 자동 복구를 적용합니다. 설정·지원 불가·입력 소스·후속 처리 오류는 호출자에게 전달합니다.
