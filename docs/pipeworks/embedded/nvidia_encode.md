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
  preserve_timestamps: false
```

YAML 값이 생성자보다 우선하며 삭제하면 최초 생성자 값으로 돌아갑니다. GPU 기본값은 0, FPS 기본값은 30, `preserve_timestamps` 기본값은 `False`입니다. 옵션은 불리언이어야 합니다. FPS는 양수여야 합니다. 기본 모드의 시간 기준 생성은 정수 FPS를 사용해야 하며 `30.0`·`29.97` 같은 실수는 처리 시작 시 오류가 발생합니다.

## 원본 타임스탬프 보존

`NvidiaEncode(preserve_timestamps=True)`로 입력 컨텍스트의 `pts`와 `time_base`를 보존합니다. `time_base`가 없으면 `video_stream.time_base`를 사용합니다. `pts`는 유효한 64비트 정수, 시간 기준은 양수여야 합니다. 선택적인 `duration`은 0 이상의 정수이며 생략하면 0입니다. B프레임을 사용하지 않으므로 출력 DTS는 입력 PTS와 같으며 원본 압축 패킷의 DTS는 재사용하지 않습니다. `fps`는 인코더 FPS·GOP·IDR 설정에 계속 사용합니다.

**원본 PTS 전달에는 수정 PyNvVideoCodec wheel이 필요합니다.** [빌드·설치 안내](../../pynvvideocodec-build.md)에 따라 `2.2.2+pipeworks.1`을 설치하면 `NvidiaDecode`가 잠긴 버퍼와 함께 얻은 `pts`와 PyAV의 `time_base`를 전달합니다. 공식 wheel에서는 `pts=None`이므로 보존 모드 입력은 폐기됩니다. 현재 입력 패킷의 PTS를 출력 프레임에 추정 대응하지 않습니다. 원본 시간이 없거나 유효하지 않은 입력은 경고와 함께 건너뛰며 FPS 기반 시간으로 대체하지 않습니다.

보존 모드는 입력당 하나의 압축 영상 패킷을 순서대로 대응합니다. 비어 있는 인코딩 결과는 시간을 소비하지 않고, 지연 출력과 종료 출력은 제출 순서의 원본 시간을 사용합니다. 대응할 입력이 없는 초과 패킷은 폐기합니다. 인코더 오류로 미출력 프레임을 버리면 해당 시간 정보도 버리며, 복구 이후에는 새 입력의 시간을 사용합니다. 프레임 누락으로 생긴 원본 시간 간격도 유지합니다.

`RTSPPublish`는 DTS가 마지막 송신 성공 DTS 이하인 패킷을 보정하지 않고 건너뜁니다. 정상 송신 패킷의 원본 PTS/DTS와 간격은 유지됩니다. PTS만 비단조이고 DTS는 증가하는 정상 재정렬 패킷은 폐기하지 않습니다.

코덱·해상도·픽셀 형식은 첫 입력에서 읽습니다. 인코더의 FPS·GOP·IDR 간격은 설정된 FPS를 사용합니다. 현재 구성에서 비트레이트와 코덱을 별도 옵션으로 지정하지 않습니다. 입력 스트림 객체나 코덱·해상도·픽셀 형식·CUDA 스트림 핸들이 바뀌면 인코더를 자동 재생성합니다. 기존 정상 인코더의 잔여 출력은 이전 스트림 정보로 전달한 뒤 교체합니다.

## 자동 복구

별도 설정 없이 복구 가능한 인코더 생성 및 프레임 인코딩 오류를 처리합니다. 실패한 프레임과 인코더는 버리고, 실패 후 최소 1초가 지난 뒤 도착하는 최신 프레임에서 인코더를 다시 생성합니다. 연속 실패에도 횟수 제한 없이 같은 방식으로 재시도합니다. 대기 중 입력 프레임은 저장하지 않고 소비하여 버리므로 일시적인 영상 정지와 프레임 누락이 있을 수 있습니다.

실패한 인코더에 EndEncode를 다시 호출하지 않습니다. 오류 복구·입력 교체·종료 시 기존 CUDA 스트림의 작업 완료를 기다린 뒤 인코더, 마지막 제출 입력, 스트림 순서로 참조를 해제합니다. 정상 프레임마다 CPU 동기화를 추가하지 않습니다. 복구용 내부 예외는 원인 문자열만 보유하여 이전 호출의 traceback이 코덱과 프레임 수명을 연장하지 않게 합니다. 입력 종료 시 복구 가능한 EndEncode 오류가 발생하면 경고를 기록하고 잔여 출력을 버립니다. 중지 요청 시에는 재시도나 종료 인코딩을 수행하지 않습니다.

H.264/HEVC는 IDR마다 필요한 영상 헤더를 반복하도록 설정합니다. 재생성한 세션은 재생 가능한 시작 프레임과 헤더를 제공합니다. 기본 모드에서는 패킷 PTS/DTS가 복구나 입력 변경 때문에 0으로 돌아가지 않고 process 시작의 FPS와 시간 기준을 유지합니다. 기본 모드의 시간은 출력 패킷 수 기준이며 버린 프레임의 실제 경과 시간을 반영하지 않습니다. 보존 모드는 새 입력의 원본 시간을 사용합니다.

오류 원인은 경고 로그로, 실제 압축 패킷 출력 재개는 정보 로그로 기록합니다. 실행 전 설정 검증·입력 소스·후속 처리 오류와 GPU 동기화 실패는 전파합니다. 실행 중 일반 네이티브·지원 불가 오류는 재시도하고 잘못된 입력·출력 패킷은 폐기합니다. Python 예외로 잡히지 않는 네이티브 프로세스 충돌이나 복구 불가능한 GPU 장애는 복구를 보장하지 않습니다.

## 패킷과 종료

빈 압축 결과는 건너뛰고, 여러 결과는 순서대로 개별 PyAV 패킷으로 전달합니다. 기본 모드에서는 각 패킷의 PTS·DTS가 0부터 증가하며 시간 기준은 FPS의 역수, 지속 시간은 1입니다. 정상 입력 종료 시 `EndEncode()`의 잔여 결과에도 선택한 시간 모드의 계약을 적용합니다.

새 컨텍스트에 감지 결과 등 임의 입력 속성을 자동으로 복사하지 않습니다. 결과를 소비하는 단계는 인코딩 앞에 둡니다. 실제 인코딩 패킷과 원본 스트림 템플릿의 RTSP 송출 호환성은 실행 환경에서 확인해야 합니다.

관련 문서: [디코딩](nvidia_decode.md), [패킷 송출](rtsp_publish.md), [파이프라인](../pipeline.md)

## 공개 API와 컨텍스트 계약

구현: `src/pipeworks/embedded/nvidia_encode.py`. 가져오기는 `from pipeworks.embedded import NvidiaEncode`이며 생성자는 `NvidiaEncode(*, gpu_id=0, fps=30, preserve_timestamps=False)`입니다. 세 옵션은 NvidiaEncode YAML 섹션으로 덮어쓰고 삭제 시 최초 생성자 값으로 돌아갑니다. fps가 0 이하이거나 preserve_timestamps가 불리언이 아니면 ValueError입니다. 기본 모드의 패킷 시간 기준은 Fraction(1, fps)로 계산하므로 양의 정수 fps를 사용합니다.

필수 입력은 frame·pixel_format·video_stream·cuda_stream입니다. processing_started_at은 프레임 처리 시간 기록에 사용하는 선택 필드입니다. 첫 입력의 스트림 코덱·너비·높이와 픽셀 형식으로 인코더를 만들고 B프레임을 끕니다. codec·bitrate·framerate는 공개 설정 키가 아닙니다.

출력은 packet과 video_stream만 가진 새 PipelineContext입니다. 원본 frame이나 사용자 속성을 복사하지 않습니다. 기본 모드의 패킷 PTS/DTS는 0부터 증가하며 duration=1, time_base=1/fps입니다. 입력 하나에서 패킷이 없거나 여러 개일 수 있고 정상 입력 종료 시 EndEncode의 잔여 패킷도 출력합니다. 보존 모드에서는 앞서 설명한 입력 시각 대응 계약을 따릅니다. 복구 가능한 네이티브 인코더 오류에는 자동 복구를 적용합니다. 실행 전 설정·입력 소스·후속 처리 및 명시적인 GPU 오류는 호출자에게 전달합니다. 잘못된 입력·패킷은 폐기하며 일반 코덱 실행 실패 후 재생성합니다.

## 비디오 메타데이터

출력 video_stream은 입력과 별개인 불변 VideoStreamInfo입니다. 첫 출력에서 실제 Annex B SPS/PPS 또는 VPS/SPS/PPS를 한 번 추출하고 이후 패킷에서 공유합니다. time_base는 패킷과 같고 기본 모드에서는 1/fps입니다. 보존 모드의 average_rate는 설정 fps이며 시간 기준이 바뀌면 새 메타데이터를 제공합니다. 입력 extradata는 재사용하지 않습니다. 인코더 교체 전 EndEncode 출력은 이전 인코더의 메타데이터를 사용합니다. repeatspspps=1로 출력 비트스트림에 헤더를 반복합니다.

## 정리 중 오류

정상 복구·교체·종료에서는 GPU 작업 완료를 기다린 후 인코더·마지막 입력·CUDA 스트림 순으로 참조를 해제합니다. 동기화가 실패하면 최초 정리 예외를 전달하고 최종 종료에서 같은 동기화를 다시 호출하지 않습니다. 이 오류는 복구 가능한 인코더 처리 예외와 구별하며 무시하거나 성공으로 처리하지 않습니다. 치명적 GPU 장애 후의 자동 컨텍스트 초기화나 프로세스 재시작 기능은 제공하지 않습니다.
