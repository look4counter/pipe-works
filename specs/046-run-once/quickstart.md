# 빠른 시작: RunOnce Step 래퍼

## 기본 사용

```python
from pipeworks import Pipeline
from pipeworks.embedded import RunOnce
from pipeworks.models import PipelineContext, Step


class Initialize(Step):
    def configure(self, config):
        pass

    def process(self, inputs):
        for context in inputs:
            context.initialized = True
            yield context


pipeline = Pipeline("example", config=config)
pipeline.step(RunOnce(Initialize()))
```

Initialize는 첫 입력에 대해서만 실행된다. 첫 실행에서 여러 컨텍스트를 내보내면 모든 출력이 전달되고, 이후 입력은 Initialize를 거치지 않고 원본 컨텍스트가 전달된다.

내부 Step 설정은 기존 방식대로 해당 클래스명 섹션에 작성한다. RunOnce 자체에는 별도 설정 항목이 없다.

