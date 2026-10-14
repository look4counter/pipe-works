# 별도 애플리케이션에서 시작하기

이 안내는 specs 없이 src와 docs를 받은 사용자를 위한 실행 절차입니다. 배포 프로젝트의 이름은 pipe-works이고 Python 가져오기 이름은 pipeworks입니다. examples는 사용 패턴이며 애플리케이션의 필수 디렉터리 이름이 아닙니다.

## 환경과 설치

현재 pyproject.toml은 Python **3.11.9**를 정확히 요구하고 PyTorch 2.2.1+cu121, torchvision 0.17.1+cu121, PyNvVideoCodec 2.2.2, TensorRT 10.10.0.31 등을 고정합니다. GPU 영상 처리·추론에는 호환되는 NVIDIA GPU·드라이버와 해당 네이티브 실행 환경이 필요합니다. 현재 설치 메타데이터에는 선택적 extras가 없고 av·torch·ultralytics·tensorrt 등이 기본 의존성입니다.

현재 main.py는 import 시 Windows 사용자 SID를 조회하고 중앙 실행에는 Windows named pipe와 msvcrt를 사용합니다. 이 배포 코드의 실행 기준은 Windows입니다. 감시 모듈의 타 운영체제 지원이 SDK 전체의 지원을 뜻하지는 않습니다.

배포 프로젝트가 D:\SDK\pipe-works에 있고 uv가 설치되어 있다고 가정합니다. 배포본에 uv.lock을 함께 두면 다음처럼 고정 환경을 준비할 수 있습니다.

```powershell
Set-Location D:\SDK\pipe-works
uv sync --locked
```

pyproject.toml의 uv 설정은 CUDA 12.1용 torch·torchvision 인덱스를 지정합니다. 일반 pip는 이 uv 설정을 읽지 않으므로 같은 환경을 만들 때 CUDA 패키지 공급 경로를 별도로 맞춰야 합니다. 배포본은 pyproject.toml·uv.lock·src·docs를 함께 제공하는 구성을 권장합니다. docs는 현재 setuptools 패키지 데이터에 포함되지 않으므로 wheel만 배포하면 이 안내가 자동으로 포함되지는 않습니다.

## 원하는 위치에 앱 만들기

```text
D:/SDK/pipe-works/
  pyproject.toml
  uv.lock
  src/pipeworks/
  docs/pipeworks/
D:/Apps/camera-app/
  app.py
  config/stream.yml
  models/
  steps/
    __init__.py
    log_packet.py
```

배포 환경의 Python으로 앱을 실행하면 설치된 pipeworks를 가져옵니다. src 내용을 앱에 복사하거나 pipeworks 폴더를 수정할 필요가 없습니다. 앱 폴더의 steps는 사용자 소유 패키지이며 이름을 자유롭게 정할 수 있습니다. 애플리케이션 파일을 pipeworks.py나 torch.py처럼 의존성과 같은 이름으로 만들면 import를 가릴 수 있습니다.

다음은 추론 모델 없이 패킷 수신과 사용자 Step 연결을 확인하는 예입니다.

steps/log_packet.py:

```python
from pipeworks.models import Step


class LogPacket(Step):
    def __init__(self):
        self._set_config_defaults(enabled=True)

    def configure(self, config):
        self.enabled = self._resolve_config(config).enabled

    def process(self, inputs):
        for item in inputs:
            if self.enabled:
                print(f"패킷 크기: {item.packet.size}")
            yield item
```

app.py:

```python
from pathlib import Path
from pipeworks import Pipeline
from pipeworks.embedded import RTSPSource
from steps.log_packet import LogPacket

BASE = Path(__file__).resolve().parent


def build_pipeline():
    return (
        Pipeline("camera", config=BASE / "config" / "stream.yml")
        .step(RTSPSource("rtsp://camera/main"))
        .step(LogPacket())
    )


if __name__ == "__main__":
    build_pipeline().run()
```

config/stream.yml:

```yaml
RTSPSource:
  reconnect: true
  reconnect_interval_ms: 3000
  transport: tcp
  timeout_ms: 5000
LogPacket:
  enabled: true
```

실제 카메라 주소로 바꾸고 다음처럼 실행합니다. steps/__init__.py는 빈 파일이어도 됩니다.

```powershell
Set-Location D:\Apps\camera-app
& D:\SDK\pipe-works\.venv\Scripts\python.exe .\app.py
```

직접 src만 참조하려면 호환 의존성을 설치한 Python 환경에서 PYTHONPATH에 SDK의 src를 추가할 수도 있습니다. src 경로만 지정하는 것으로 의존성이 설치되지는 않습니다.

```powershell
$env:PYTHONPATH = "D:\SDK\pipe-works\src;D:\Apps\camera-app"
python D:\Apps\camera-app\app.py
```

## 영상과 추론 연결

압축 패킷은 RTSPSource → RTSPPublish로 전달합니다. 프레임 처리는 RTSPSource → NvidiaDecode → 사용자 영상 처리 → NvidiaEncode → RTSPPublish 순서로 연결합니다. 추론은 전처리 → YoloInference → 후처리 순서이며 전후처리는 모델에 맞게 앱에서 제공해야 합니다. 코어는 YOLO 전후처리·Overlay를 제공하지 않습니다. examples의 파일을 사용할 경우 그 파일과 관련 도우미도 앱 패키지에 포함하고 import 경로를 앱에 맞춥니다.

YoloInference의 backend는 반드시 지정합니다. 모델 경로는 BASE / "models" / "model.pt"처럼 절대경로로 만들고, 설정 파일은 실행 전에 생성합니다. Pipeline 생성 시 파일을 읽으므로 없는 설정 파일은 오류입니다. 설정이 없으면 내용이 {}인 파일을 제공합니다.

## 배치와 사용자 모듈

batch=True인 YoloInference가 래퍼 내부에 하나라도 있으면 **전체** 파이프라인이 중앙 프로세스로 전달됩니다. 생성자에는 열린 연결·GPU 모델·직렬화할 수 없는 잠금 대신 설정을 보관하고 실제 자원은 process에서 지연 생성합니다. backend="my_backends:MyBackend"처럼 문자열로 참조하는 모듈은 중앙 프로세스에서도 import 가능해야 합니다.

중앙 프로세스는 사용자 Step을 cloudpickle로 전달하지만 임의 패키지·동적 import 경로·모델 파일을 모두 배포해 주지는 않습니다. 앱을 설치 가능한 패키지로 같은 Python 환경에 설치하거나, 중앙 프로세스를 처음 시작하기 전에 앱 경로를 PYTHONPATH에 설정합니다. 이미 실행 중인 중앙 프로세스는 새 PYTHONPATH를 상속하지 않습니다. 연결이 모두 끝나 자동 종료된 뒤 다시 실행하거나 개발 모드를 사용합니다.

[설정과 경로](configuration.md), [사용자 Step](custom_steps.md), [실행부 확장](yolo_backend.md), [중앙 프로세스](main.md), [문제 해결](troubleshooting.md)을 이어서 참고하세요.
