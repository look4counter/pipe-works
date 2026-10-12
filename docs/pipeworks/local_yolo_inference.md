# 공유 GPU 모델 배치 추론

**파일 위치:** src/pipeworks/local_yolo_inference.py

이 모듈은 준비된 배치 1 GPU 입력을 같은 중앙 프로세스의 모델별 작업자에 제출합니다. 영상의 색 변환·리사이즈·NMS는 examples/step/yolo_pre_process.py와 yolo_post_process.py에서 처리합니다.

## 파이프라인 조합

examples가 모듈 탐색 경로에 있을 때 다음처럼 연결합니다.

```python
from pathlib import Path
from pipeworks import Backend
from pipeworks.embedded import YoloInference
from step.yolo_pre_process import YoloPreProcess
from step.yolo_post_process import YoloPostProcess

pipeline.step(YoloPreProcess())
pipeline.step(YoloInference(Path("models/yolo11n.pt"), backend=Backend.ULTRALYTICS, batch=True))
pipeline.step(YoloPostProcess())
```

## 직접 호출

infer(model_path, inputs, gpu_id=0, *, backend="torchscript", profile_index=0, ready_event=None, on_inference_complete=None, on_profile_complete=None)는 GPU 텐서 또는 이름별 GPU 텐서 사전을 받아 이름별 원시 GPU 출력 사전을 반환합니다. 입력의 첫 축은 1이어야 합니다. 영상 입력이나 최종 감지 결과를 직접 받거나 반환하지 않습니다.

실행부·GPU·profile·입력 이름/자료형/비배치 형상이 다른 요청은 섞이지 않습니다. 각 결과는 요청별 GPU 복사본입니다. 오류가 나면 해당 세션을 제거하고 네이티브 자원을 닫아 다음 요청에서 재로드합니다.

## 배치 설정

모델 동명 .yml에서 max_batch_size와 timeout_ms를 지정합니다. 파일이 없으면 크기 1과 대기 0을 사용합니다. TensorRT는 plugins를 지원하며 생략한 배치 값도 기본값을 사용합니다. 다른 실행부는 설정 파일이 있으면 두 배치 값을 모두 요구합니다. profile_index는 TensorRT에서만 0 이외의 값을 지정할 수 있습니다.

캐시된 작업자는 이미 로드한 모델을 재사용합니다. 최초 준비에는 파일이 필요하며 이미 로드된 모델은 파일 삭제 후에도 계속 사용할 수 있습니다. 설정 변경 반영에는 공유 작업자가 있는 프로세스를 다시 시작합니다.

관련 안내: [GPU 원시 추론](embedded/yolo_inference.md)
