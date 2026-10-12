# Models: 핵심 데이터 구조

파이프라인의 기본 데이터 타입과 추상 클래스를 정의합니다.

**파일 위치:** `src/pipeworks/models.py`

---

## 📚 개요

이 모듈은 두 가지 핵심 개념을 제공합니다:

1. **PipelineContext**: 스트림의 각 "데이터 단위" (프레임, 패킷)
2. **Step**: 파이프라인의 기본 블록 (추상 클래스)

---

## 🔑 핵심 클래스

### PipelineContext

스트림 데이터를 담는 컨테이너입니다. 동적으로 필드를 추가할 수 있습니다.

```python
from pipeworks.models import PipelineContext

# Source Step에서 생성
context = PipelineContext(video_stream=video_stream, packet=packet)

# Processing Step에서 필드 추가
context.detections = {"yolo11n.pt": yolo_results}
context.custom_field = "value"

# 다음 Step에서 접근
print(context.detections)
print(context.custom_field)
```

#### 특징

- **동적 속성**: `SimpleNamespace` 기반이므로 자유롭게 속성 추가 가능
- **체이닝 친화적**: 각 Step이 context를 수정하고 전달
- **타입 안전하지 않음**: 동적이므로 속성 존재 확인 필요

#### 일반적인 필드들

```python
from pipeworks import Backend
from step.yolo_pre_process import YoloPreProcess
from step.yolo_post_process import YoloPostProcess

# RTSPSource에서 생성
context.video_stream  # av.VideoStream
context.packet  # av.Packet

# NvidiaDecode에서 생성한 새 컨텍스트
context.frame  # GPU 프레임
context.pixel_format  # 픽셀 형식 (예: NV12)
context.cuda_stream  # 영상 처리 CUDA 스트림
context.processing_started_at  # 후속 처리 시작 시각, perf_counter 기준

# YoloInference 또는 예제 TensorRT 후처리에서 추가
context.detections  # {모델 ID: 결과 또는 None}

# TensorRT 전처리·추론의 임시 속성
context.model_input  # GPU 텐서 또는 이름별 GPU 텐서 사전
context.model_output  # 이름별 GPU 출력 사전 또는 None
context.model_id  # 모델 실행 ID, 후처리에서 정리
```

`StreamReport`는 실행별 수집기의 통계를 읽으며 컨텍스트에 개별 추론 시간이나 수신 시각 필드를 추가하지 않습니다. 디코더·인코더가 새 컨텍스트를 만들 때 임의 입력 속성을 자동 승계하지 않습니다.

#### 필드 접근 패턴

```python
# 1. 직접 접근 (필드 존재한다고 가정)
detections = context.detections

# 2. 안전한 접근 (필드 없으면 None)
detections = getattr(context, "detections", None)

# 3. 필드 존재 확인
if hasattr(context, "detections"):
    print(context.detections)

# 4. 모든 필드 조회
print(vars(context))  # dict 반환
```

---

### Step

모든 파이프라인 Step의 추상 기본 클래스입니다.

`configure()`와 `process()`는 모두 필수 구현 추상 메서드입니다. 구현을 생략하면 생성 시 `TypeError`가 발생합니다. 구체 구현을 상속해도 되며 설정이 필요 없으면 빈 `configure()`를 제공합니다.

```python
from pipeworks.models import Step, PipelineContext
from typing import Iterator
from types import SimpleNamespace


class MyStep(Step):
    def configure(self, config: SimpleNamespace) -> None:
        """YAML 설정을 읽어서 자신의 속성을 설정합니다."""
        pass

    def process(self, inputs: Iterator[PipelineContext]) -> Iterator[PipelineContext]:
        """입력을 받아 처리 후 출력합니다."""
        yield from inputs
```

#### configure(config) 메서드

**목적**: YAML 파일에서 읽은 설정을 Step에 적용합니다.

```yaml
# config.yaml
MyStep:
  threshold: 0.5
  gpu_id: 0
  max_batch_size: 32
```

```python
class MyStep(Step):
    def __init__(self):
        self.threshold = 0.5  # 기본값
        self.gpu_id = 0
        self.max_batch_size = 32

    def configure(self, config: SimpleNamespace) -> None:
        # config는 YAML의 "MyStep" 섹션
        self.threshold = getattr(config, "threshold", 0.5)
        self.gpu_id = getattr(config, "gpu_id", 0)
        self.max_batch_size = getattr(config, "max_batch_size", 32)

    def process(self, inputs):
        yield from inputs
```

**호출 시점:**
- `Pipeline.step()` 등록 시 (초기 구성)
- Hotswap으로 config.yaml이 변경됨 (재구성)

#### process(inputs) 메서드

**목적**: 입력 스트림을 처리하여 출력합니다.

```python
def process(self, inputs: Iterator[PipelineContext]) -> Iterator[PipelineContext]:
    for context in inputs:
        # 1. 이전 Step의 결과 읽기
        if hasattr(context, "detections"):
            detections = context.detections

        # 2. 처리
        result = self.my_processing(context)

        # 3. 결과를 context에 저장
        context.my_result = result

        # 4. 다음 Step으로 전달
        yield context
```

**특징:**
- **Generator 기반**: `yield`를 사용하여 지연 처리
- **Streaming**: 메모리 효율적 (전체 배열을 메모리에 로드하지 않음)
- **일반 동기 연결**: 후속 단계의 입력 요청에 맞춰 상류를 소비
- **백그라운드 단계**: `NvidiaDecode`, `TapSkipIfBusy`, `CudaAsync`는 큐·건너뜀·폐기 정책이 있으므로 각 단계의 계약을 확인

#### 에러 처리

```python
class RobustStep(Step):
    def configure(self, config):
        pass

    def process(self, inputs: Iterator[PipelineContext]) -> Iterator[PipelineContext]:
        for context in inputs:
            try:
                result = self.my_processing(context)
                context.result = result
            except Exception as error:
                # 에러를 기록하되 파이프라인 계속 실행
                import logging

                logging.error(f"처리 실패: {error}")
                # context를 그대로 전달 또는 스킵
                yield context  # 계속 진행
                # 또는: continue  # 스킵
            else:
                yield context
```

---

## 🎯 실제 사용 패턴

### 패턴 1: Simple Pass-Through

```python
class LogStep(Step):
    def configure(self, config: SimpleNamespace) -> None:
        self.verbose = getattr(config, "verbose", False)

    def process(self, inputs: Iterator[PipelineContext]) -> Iterator[PipelineContext]:
        for context in inputs:
            if self.verbose:
                print(f"Processing: {vars(context)}")
            yield context
```

### 패턴 2: 필터링

```python
class FilterStep(Step):
    def configure(self, config: SimpleNamespace) -> None:
        pass

    def process(self, inputs: Iterator[PipelineContext]) -> Iterator[PipelineContext]:
        for context in inputs:
            results = getattr(context, "detections", None)
            if results is None:
                yield context
            elif any(
                result is not None and len(result.boxes) > 0
                for result in results.values()
            ):
                yield context
```

### 패턴 3: 데이터 변환

```python
class TransformStep(Step):
    def configure(self, config: SimpleNamespace) -> None:
        self.scale = getattr(config, "scale", 1.0)

    def process(self, inputs: Iterator[PipelineContext]) -> Iterator[PipelineContext]:
        for context in inputs:
            # 데이터 변환
            if hasattr(context, "data"):
                context.scaled_data = context.data * self.scale
            yield context
```

### 패턴 4: 일괄 처리 (Batch)

```python
class BatchStep(Step):
    def configure(self, config: SimpleNamespace) -> None:
        self.batch_size = getattr(config, "batch_size", 32)

    def process(self, inputs: Iterator[PipelineContext]) -> Iterator[PipelineContext]:
        batch = []
        for context in inputs:
            batch.append(context)

            if len(batch) >= self.batch_size:
                # 배치 처리
                results = self.process_batch(batch)
                for result in results:
                    yield result
                batch = []

        # 마지막 배치 처리 (불완전한 배치)
        if batch:
            results = self.process_batch(batch)
            for result in results:
                yield result

    def process_batch(self, batch):
        # 배치 처리 로직
        return batch  # 또는 변환된 배치
```

---

## 🔗 관련 문서

- [Pipeline](pipeline.md): 파이프라인 조립 및 실행
- [Hotswap](hotswap.md): 실행 중 코드/설정 재로드
- [RTSPSource](embedded/rtsp_source.md): Source Step 예제
- [YoloInference](embedded/yolo_inference.md): Processing Step 예제

---

## 💡 TIP

1. **필드 접근 시 `getattr()` 사용**: context 필드가 없을 수도 있으니 안전하게 접근
2. **Generator 사용**: 메모리 효율적인 스트리밍 처리
3. **에러 처리**: 한 context의 에러가 전체 파이프라인을 중단하지 않도록
4. **필드 이름 충돌 방지**: Custom field 이름은 명확하게 (e.g., `my_custom_result` 아니면 `result`)
