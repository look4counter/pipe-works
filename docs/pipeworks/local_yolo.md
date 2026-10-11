# LocalYolo: 공유 GPU YOLO 배치 추론

**파일 위치:** `src/pipeworks/local_yolo.py`

이 모듈은 같은 프로세스에서 모델별 작업자와 요청 큐를 공유합니다. 일반 파이프라인에서는 `YoloDetect(model_path, batch=True)`를 사용하며, 영상 처리와 공유 작업자는 선택한 중앙 프로세스에서 실행됩니다.

## 파이프라인에서 사용

모델 파일을 미리 준비하고 경로를 지정합니다.

```python
from pathlib import Path
from pipeworks import Pipeline
from pipeworks.embedded import (
    RTSPSource,
    NvidiaDecode,
    YoloDetect,
    NvidiaEncode,
    RTSPPublish,
)

pipeline = Pipeline("yolo-pipeline", config=Path("config.yaml"))
pipeline.step(RTSPSource("rtsp://camera/main"))
pipeline.step(NvidiaDecode())
pipeline.step(YoloDetect(Path("models/yolo11n.pt"), batch=True))
pipeline.step(NvidiaEncode())
pipeline.step(RTSPPublish("rtsp://mediamtx:8554/output"))
pipeline.run()
```

## 배치 수집 설정

모델 동명 `.yml` 파일에서 최대 크기와 수집 시간을 읽습니다. 파일이 없으면 배치 크기 1, 수집 시간 0입니다. 파일이 있으면 다음 두 값을 모두 지정합니다.

```yaml
max_batch_size: 8
timeout_ms: 20
```

`max_batch_size`는 양의 정수, `timeout_ms`는 0 이상의 유한한 밀리초 값입니다. 이전 `timeout` 키는 오류로 거부합니다. 수집 시간은 추론의 실행 제한 시간이 아닙니다. 클래스 필터·신뢰도·GPU 번호가 같은 요청을 묶으며 실행 중 모델 YAML 변경을 반영하려면 공유 작업자가 있는 프로세스를 다시 시작합니다.

## 직접 호출

`infer(model_path, image, classes, confidence, gpu_id, *, ready_event=None, on_inference_complete=None, on_profile_complete=None)`는 GPU 입력을 제출하고 결과 준비까지 기다립니다. 입력은 독립된 FP32 CHW RGB 텐서 또는 기존 GPU NV12 텐서입니다. RGB는 0~1 범위의 픽셀 값을 사용합니다. 원본 입력의 수명과 생산 스트림 준비 이벤트는 호출자가 보장해야 합니다.

반환값은 원본 해상도로 좌표를 복원한 단일 Ultralytics 결과 객체입니다. `YoloDetect`의 `detections[id]` 사전 저장은 Step에서 수행합니다. 입력 영상과 박스는 GPU에 유지되며 실패는 호출자에게 예외로 전달됩니다.

## 공유 작업자의 경로 검사

작업자 최초 준비 시 경로를 정규화하고 파일 존재를 검사합니다. 같은 입력 경로를 다시 사용하면 캐시된 작업자를 찾아 `resolve/is_file`을 생략합니다. 상대경로는 호출 작업 디렉터리별로 구분하며, 같은 정규 경로는 작업자를 공유합니다. 이미 로드된 모델은 파일 삭제 후에도 사용할 수 있고 캐시된 링크의 대상 변경은 자동 재로드를 유발하지 않습니다. 새 모델 로드에는 실제 파일이 필요합니다.

관련 문서: [YOLO 개별·공유 배치 감지](embedded/yolo_detect.md), [파이프라인](pipeline.md)
