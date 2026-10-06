### 1. 요구사항

1. Python 3.11.9
2. uv 패키지 관리자
3. Windows 운영체제
4. NVIDIA GPU 및 호환되는 NVIDIA 드라이버
5. RTSP 입력 영상 및 송출용 RTSP 서버

### 2. Examples

#### 모델 다운로드

```powershell
PS> uv sync
PS> curl.exe -L https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt -o examples\model\yolo11n.pt
PS> uv run yolo export model=examples/model/yolo11n.pt format=engine batch=10 dynamic=True imgsz=640 device=0
```

#### 예제 실행

```powershell
PS> .\.venv\Scripts\python.exe .\examples\01_single_stream_rtsp_style.py
```

### 3. 기본으로 제공되는 Step

| Step              | 생성 방법                     | 설명                                                            |
| ----------------- | ----------------------------- | --------------------------------------------------------------- |
| `RTSPSource`      | `RTSPSource(url)`             | RTSP 영상의 압축 패킷을 수신합니다.                             |
| `RTSPPublish`     | `RTSPPublish(url)`            | 압축 패킷을 RTSP 서버로 송출합니다.                             |
| `NvidiaDecode`    | `NvidiaDecode()`              | NVIDIA GPU로 압축 패킷을 영상 프레임으로 디코딩합니다.          |
| `NvidiaEncode`    | `NvidiaEncode()`              | NVIDIA GPU로 영상 프레임을 압축 패킷으로 인코딩합니다.          |
| `YoloDetectBatch` | `YoloDetectBatch(model_path)` | 같은 모델을 사용하는 요청을 모아 YOLO 배치 추론을 수행합니다.   |
| `Sink`            | `Sink(step)`                  | 전달된 Step을 별도 스레드에서 실행되도록 만듭니다.              |
| `StreamReport`    | `StreamReport()`              | 수신·송신 상태, FPS, 프레임 처리 시간과 추론 통계를 출력합니다. |

### 4. 사용자 정의 Step

사용자 정의 Step은 아래와 같이 생성할 수 있습니다.

```python
# my_step.py

from pipeworks import Step

class MyStep(Step):
    def configure(self, config: SimpleNamespace) -> None:
        self.param1 = getattr(config, "param1", "Default Value")
        self.param2 = getattr(config, "param2", True)
        pass

    def process(self, inputs: Iterator[PipelineContext]) -> Iterator[PipelineContext]:
        for input in inputs:
            print(f"Param1: {self.param1}")
            print(f"Param2: {self.param2}")
            yield input
```

```yml
# stream.yml

...

MyStep:
  param1: Custom Value
  param2: false

...

```

사용자 정의 Step은 HotSwap 기능을 항상 지원합니다. 파일 수정 시 재시작없이 변경된 값이 적용됩니다.