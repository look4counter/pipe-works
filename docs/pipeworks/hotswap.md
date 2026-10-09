# Hotswap: 실행 중 코드/설정 재로드

파이프라인을 중단하지 않고 Step의 코드와 설정을 실시간으로 변경할 수 있습니다.

**파일 위치:** `src/pipeworks/hotswap.py`

---

## 📚 개요

Hotswap은 다음을 자동으로 감지하고 적용합니다:

1. **설정 변경**: `config.yaml` 수정 → `configure()` 재호출
2. **코드 변경**: Step의 `.py` 파일 수정 → Step 클래스 재로드

이를 통해 파이프라인이 실행 중에도 빠르게 개발할 수 있습니다.

---

## 🔄 동작 방식

### 주기적 감시 (Check Interval)

```
파이프라인 시작
    ↓
매 데이터마다 또는 0.5초마다 확인
    - config.yaml 파일 해시 확인 (변경됐나?)
    - Step .py 파일 해시 확인 (변경됐나?)
    ↓
변경 감지 → 새 Step으로 재로드
    ↓
진행 중인 context는 원래 Step으로 계속 처리
새 context는 새로운 Step으로 처리
```

### Epoch (시간대)

내부적으로 "Epoch"라는 개념을 사용합니다:

```
Context (Epoch 1)
Context (Epoch 1)
[코드 변경 감지]
Context (Epoch 2)  ← 새 Step으로 처리
Context (Epoch 2)
```

---

## 📝 설정 재로드

### config.yaml 변경 시 자동 반영

**초기 config.yaml:**
```yaml
YoloDetect:
  confidence: 0.25
  gpu_id: 0
  inference_interval_frame: 1
```

파이프라인 실행 중:

```yaml
YoloDetect:
  confidence: 0.5      # 변경
  gpu_id: 0
  inference_interval_frame: 2  # 변경
```

파일을 저장하면:
1. Pipeline이 변경 감지
2. YoloDetect Step의 `configure()` 호출
3. 새로운 설정이 적용됨

### 실제 코드 예제

```python
from types import SimpleNamespace
from typing import Iterator
from pipeworks.models import PipelineContext, Step
import logging

logger = logging.getLogger(__name__)

class ConfigurableStep(Step):
    def __init__(self):
        self.threshold = 0.5
        self.debug = False
    
    def configure(self, config: SimpleNamespace) -> None:
        # YAML의 변경을 감지하고 여기서 적용됨
        old_threshold = self.threshold
        self.threshold = getattr(config, 'threshold', 0.5)
        self.debug = getattr(config, 'debug', False)
        
        if self.threshold != old_threshold and self.debug:
            logger.info(f"Threshold 변경: {old_threshold} → {self.threshold}")
    
    def process(self, inputs: Iterator[PipelineContext]) -> Iterator[PipelineContext]:
        for context in inputs:
            if self.debug:
                logger.debug(f"Processing with threshold={self.threshold}")
            # ...
            yield context
```

**config.yaml:**
```yaml
ConfigurableStep:
  threshold: 0.5
  debug: false
```

**실행 중 config.yaml 수정:**
```yaml
ConfigurableStep:
  threshold: 0.7  # 변경됨
  debug: true     # 로깅 활성화
```

→ 자동으로 적용됨

---

## 💻 코드 재로드

### Step 파일 변경 시 재로드

**my_step.py (초기 버전):**
```python
from types import SimpleNamespace
from typing import Iterator
from pipeworks.models import PipelineContext, Step

class MyDetector(Step):
    def configure(self, config: SimpleNamespace) -> None:
        self.sensitivity = getattr(config, 'sensitivity', 0.5)
    
    def process(self, inputs: Iterator[PipelineContext]) -> Iterator[PipelineContext]:
        for context in inputs:
            # 초기 로직
            context.score = 0.5
            yield context
```

파이프라인 실행 중 파일 수정:

```python
class MyDetector(Step):
    def configure(self, config: SimpleNamespace) -> None:
        self.sensitivity = getattr(config, 'sensitivity', 0.5)
    
    def process(self, inputs: Iterator[PipelineContext]) -> Iterator[PipelineContext]:
        for context in inputs:
            # 수정된 로직
            context.score = 0.8  # 변경됨
            context.extra_info = "new field"  # 새 필드 추가
            yield context
```

파일을 저장하면:
1. Hotswap이 파일 변경 감지
2. 새로운 MyDetector 클래스 로드
3. 새 context부터 새로운 코드로 처리
4. 이전 context는 원래 코드로 계속 처리

### 타이밍 주의

```
Context 1 (old code)  ← 처리 중
  ↓ (파일 저장)
[Hotswap 감지]
  ↓
Context 2 (new code)  ← 새로운 코드로 처리
Context 3 (new code)
```

---

## 🎯 개발 워크플로우

### 추천 패턴

1. **먼저 config.yaml로 파라미터 조정**

```yaml
MyStep:
  sensitivity: 0.5
  batch_size: 32
```

파이프라인이 실행 중인 상태에서 YAML 파일만 수정:
```yaml
MyStep:
  sensitivity: 0.7  # 바꾸고 저장 → 즉시 반영
  batch_size: 64
```

2. **그 다음 Step 코드 개선**

Step 로직을 수정하고 저장 → 자동으로 재로드

3. **공통 라이브러리는 일반 방법 사용**

Hotswap은 현재 Step만 재로드하므로, 공통 코드 변경 시 수동 재시작 필요

---

## ⚙️ 고급 사용법

### 변경 감지 간격 조정

```python
from pathlib import Path
from pipeworks import Pipeline
from pipeworks.hotswap import Hotswap
from my_step import MyStep

pipeline = Pipeline("dev-pipeline", config=Path("config.yaml"))

# Hotswap의 check_interval 직접 설정 (초 단위)
step = Hotswap(
    MyStep(),
    check_interval=1.0  # 1초마다 확인 (기본값: 0.5초)
)
pipeline.step(step)
pipeline.run()
```

### 코드 재로드 비활성화

설정만 변경하고 코드는 재로드하지 않으려면:

```python
from pipeworks.hotswap import Hotswap
from my_step import MyStep

step = Hotswap(
    MyStep(),
    watch_code=False  # 코드 변경 감시 비활성화
)
```

### 에러 복구 비활성화

기본적으로 Step 실행 중 에러가 발생하면 자동으로 복구를 시도합니다:

```python
from pipeworks.hotswap import Hotswap
from my_step import MyStep

step = Hotswap(
    MyStep(),
    recover_errors=False  # 에러 복구 비활성화 (즉시 파이프라인 중단)
)
```

---

## 🛠️ 상태 보존 (State Preservation)

### 상태가 필요한 Step

```python
class StatefulStep(Step):
    def __init__(self):
        self.model = None
        self.cache = {}
    
    def configure(self, config: SimpleNamespace) -> None:
        pass
    
    def process(self, inputs: Iterator[PipelineContext]) -> Iterator[PipelineContext]:
        if self.model is None:
            # 모델을 한 번만 로드
            self.model = load_expensive_model()
        
        for context in inputs:
            if context.id not in self.cache:
                self.cache[context.id] = expensive_computation(context)
            
            context.cached = self.cache[context.id]
            yield context
```

Hotswap 재로드 시:
- 기본적으로 상태는 보존되지 않음 (새로운 인스턴스 생성)
- 모델 재로드는 비효율적이므로 주의

### 최적화: 상태 유지

설정 변경만 필요한 경우 코드 재로드를 비활성화:

```yaml
# config.yaml만 변경되는 경우
StatefulStep:
  param: value  # 이것만 변경
```

```python
step = Hotswap(
    MyStep(),
    watch_code=False  # 코드 재로드 X, 설정만 적용
)
```

---

## 🔗 관련 문서

- [Pipeline](pipeline.md): 파이프라인 조립
- [Models](models.md): Step과 PipelineContext
- [Embedded Steps](../embedded/): 내장 Step 구현

---

## 💡 TIP

1. **개발할 때 유용**: 파이프라인을 재시작하지 않고 빠르게 테스트
2. **프로덕션 안정성**: 필요 시 Hotswap 기능 비활성화 가능
3. **상태 주의**: 중요한 상태는 Step 내부보다 context에 저장
4. **로깅**: 언제 재로드되는지 파악하기 위해 로깅 추가 권장
