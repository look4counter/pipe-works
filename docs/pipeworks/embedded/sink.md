# Sink: 파이프라인 종료점

파이프라인의 마지막 Step으로, 최종 데이터를 처리합니다.

**파일 위치:** `src/pipeworks/embedded/sink.py`  
**역할**: Sink Step (최종 처리)

---

## 📚 개요

- 파이프라인의 마지막 Step
- 다른 Step을 래핑하여 종료점으로 사용
- 커스텀 후처리 로직 적용

---

## 🔑 사용법

```python
from pipeworks import Pipeline
from pipeworks.embedded import RTSPSource, YoloDetect, Sink
from my_module import MyFinalStep

pipeline = Pipeline("pipeline", config=Path("config.yaml"))
pipeline.step(RTSPSource(url="rtsp://camera"))
pipeline.step(YoloDetect(model_path=Path("models/yolov8n.pt")))
pipeline.step(Sink(step=MyFinalStep()))
pipeline.run()
```

### Custom Final Step

```python
from types import SimpleNamespace
from typing import Iterator
from pipeworks.models import PipelineContext, Step

class MyFinalStep(Step):
    def configure(self, config: SimpleNamespace) -> None:
        pass
    
    def process(self, inputs: Iterator[PipelineContext]) -> Iterator[PipelineContext]:
        for context in inputs:
            # 최종 처리 (저장, 로깅 등)
            if context.detections is not None:
                print(f"감지된 객체: {len(context.detections)}")
            yield context  # 또는 yield 안 함 (파이프라인 종료)
```

---

## 🔗 관련 문서

- [Models](../models.md): Step 구조
- [Pipeline](../pipeline.md): 파이프라인 조립
