# RunOnce Step 사용법

RunOnce는 내부 Step을 래퍼 인스턴스마다 최초 입력에 한 번만 실행한다. 내부 Step의 출력은 첫 실행에서 모두 전달하고, 이후 입력은 내부 Step을 거치지 않고 그대로 전달한다.

## 사용 예시

```python
import os
from pathlib import Path

from pipeworks.embedded import RunOnce
from pipeworks.models import Step

PID_FILE = Path(".agent.pid")


class Initialize(Step):
    def configure(self, config):
        pass

    def process(self, inputs):
        pid = os.getpid()
        PID_FILE.write_text(f"{pid}\n", encoding="utf-8")
        print(f"Initialize를 프로세스 {pid}에서 한 번 실행했습니다.")
        for context in inputs:
            yield context


pipeline.step(RunOnce(Initialize()))
```

입력이 비어 있으면 Initialize는 실행되지 않는다. 최초 실행에서 예외가 발생하면 예외가 호출자에게 전달되며, 다음 처리에서 다시 시도할 수 있다.

RunOnce에는 별도 YAML 설정이 없다. 내부 Step 설정은 기존처럼 내부 Step 클래스명 섹션에 작성한다. 실행 상태는 인스턴스별 메모리 상태이므로 프로세스 간에 공유되지 않는다.
