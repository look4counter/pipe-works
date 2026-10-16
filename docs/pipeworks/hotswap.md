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

### 공유 OS 감시와 처리 경계 확인

```
파이프라인 시작
    ↓
프로세스별 공유 OS 감시기가 코드·YAML의 변경 표시
    ↓
처리 경계에서 기본 0.5초 간격으로 확인
    - 변경 표시가 없으면 공유 스냅샷 사용 (파일 읽기 없음)
    - 변경 표시가 있으면 파일을 읽고 해시·내용을 공유
    ↓
변경 감지 → 새 Step으로 재로드
    ↓
진행 중인 context는 원래 Step으로 계속 처리
새 context는 새로운 Step으로 처리
```

`watchdog`가 Windows에서는 Windows API, Linux에서는 inotify 등 OS 변경 알림을 사용합니다. 같은 디렉터리의 감시와 같은 파일의 내용·해시는 실행 프로세스 안에서 공유합니다. 수정·생성·삭제·이동 저장을 처리하며 콜백은 변경 표시만 남깁니다. 코드 준비와 설정 적용은 기존 처리 경계에서 수행합니다.

알림 없이 놓친 변경은 30초 간격의 공유 내용 재검사 이후 첫 처리 경계에서 발견합니다. 감시 시작·등록 실패나 스레드 종료 시 재등록을 시도하고 0.5초 재검사로 보완합니다. 재검사는 수정 시각·크기 보존 여부와 관계없이 내용을 확인합니다. 파일 읽기나 새 코드·설정에 오류가 있으면 기존 동작을 유지합니다.

`check_interval`은 처리 경계의 확인 제한입니다. 명시적으로 `check_interval=0`을 지정하면 매 확인마다 내용을 다시 읽는 기존 즉시 검사 동작을 유지합니다. 처리 종료 시 구독을 닫고 마지막 사용자가 해제하면 감시 스레드를 정리합니다. 별도 프로세스에는 파일 경로만 전달하고 실행 프로세스에서 감시 자원을 생성합니다.

### Epoch (시간대)

내부적으로 "Epoch"라는 개념을 사용합니다:

`TapSkipIfBusy`에서는 배경 작업을 수락할 때 별도 컨텍스트를 만들어 변경 정보를 분리합니다. 배경 Step의 코드 교체가 주 경로의 상류 변경으로 잘못 전달되어 주 경로 상태를 초기화하지 않습니다. 분기 이전의 공통 상류 변경 정보는 양쪽에 보존합니다. 같은 파일을 감시하는 Step들은 파일 변경을 각자 감지하는 기존 동작을 유지합니다.

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
YoloInference:
  backend: ultralytics
  gpu_id: 0

YoloPostProcess:
  confidence: 0.25

```

파이프라인 실행 중:

```yaml
YoloInference:
  backend: ultralytics
  gpu_id: 0

YoloPostProcess:
  confidence: 0.5      # 변경

```

파일을 저장하면:
1. Pipeline이 변경 감지
2. 변경된 섹션에 해당하는 YoloInference 또는 YoloPostProcess Step의 `configure()` 호출
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
        self.threshold = getattr(config, "threshold", 0.5)
        self.debug = getattr(config, "debug", False)

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
        self.sensitivity = getattr(config, "sensitivity", 0.5)

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
        self.sensitivity = getattr(config, "sensitivity", 0.5)

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
    check_interval=1.0,  # 1초마다 확인 (기본값: 0.5초)
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
    watch_code=False,  # 코드 변경 감시 비활성화
)
```

### 에러 복구 비활성화

기본적으로 Step 실행 중 에러가 발생하면 자동으로 복구를 시도합니다:

```python
from pipeworks.hotswap import Hotswap
from my_step import MyStep

step = Hotswap(
    MyStep(),
    recover_errors=False,  # 에러 복구 비활성화 (즉시 파이프라인 중단)
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
- 새 인스턴스를 만들고 이전 인스턴스의 속성 사전을 얕게 복사하므로 속성에 저장한 모델·캐시를 보존합니다.
- 최신 설정은 `configure()`로 다시 적용합니다. 처리 생성기의 지역 상태는 새 실행 구간에서 다시 시작합니다.
- 생성자에서만 수행한 초기화에 의존하지 않도록 새 코드가 기존 속성을 사용할 수 있어야 합니다.

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
    watch_code=False,  # 코드 재로드 X, 설정만 적용
)
```

---

## 🔗 관련 문서

- [Pipeline](pipeline.md): 파이프라인 조립
- [Models](models.md): Step과 PipelineContext
- [Embedded Steps](embedded/): 내장 Step 구현

---

## 💡 TIP

1. **개발할 때 유용**: 파이프라인을 재시작하지 않고 빠르게 테스트
2. **프로덕션 안정성**: 필요 시 Hotswap 기능 비활성화 가능
3. **상태 주의**: 중요한 상태는 Step 내부보다 context에 저장
4. **로깅**: 언제 재로드되는지 파악하기 위해 로깅 추가 권장

프레임 실행 간격은 [EveryNFrames](embedded/every_n_frames.md)로 묶고 해당 YAML 섹션의 `interval_frames`를 변경합니다. 내부 사용자 Step도 코드와 클래스명 YAML 변경을 감시합니다.

## 공개 생성자와 입출력 계약

`Hotswap(step, *, check_interval=0.5, source=False, watch_code=True, recover_errors=True)`

| 옵션 | 기본값 | 의미 |
| --- | --- | --- |
| step | 필수 | 감쌀 Step |
| check_interval | 0.5 | 처리 경계에서 코드·설정 확인을 제한하는 초 단위 간격. 음수는 ValueError |
| source | False | True이면 상류 입력 대신 빈 반복자로 소스를 실행 |
| watch_code | True | 감쌀 Step 파일의 코드 변경 감시 여부 |
| recover_errors | True | 내부 실행 오류의 복구 여부 |

옵션은 생성자에서 지정합니다. configure의 설정은 Hotswap 자체 옵션이 아니라 감싼 Step에 전달합니다. Pipeline에 명시적으로 등록한 Hotswap은 감싼 클래스명의 YAML 섹션을 사용하며 첫 Step이면 source=True로 설정합니다. 내장 Step은 자동 코드 교체 대상에서 제외하고 설정 감시를 적용합니다.

입출력 필드는 감싼 Step의 계약을 따릅니다. 출력에 내부 epoch 표식을 붙여 하류가 실행 구간의 변화를 인식하게 합니다. 일반 모드의 복구 시 아직 출력되지 않은 입력의 속성 사전을 원래 값으로 복원해 전달하지만, 얕은 사본이므로 텐서·중첩 객체의 제자리 수정까지 되돌리지는 않습니다. 상류에서 발생한 예외는 복구하지 않고 전달합니다. source=True의 복구는 원본 전달 대신 Step을 다시 만들고 0.1초 후 재시도합니다.

종료·재시작 시 내부 출력 반복자를 닫고 감시 구독을 해제합니다. 일반 모드에서는 상류 반복자도 닫습니다.
