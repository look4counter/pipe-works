# Backend: 실행부 선택

구현: src/pipeworks/backend.py. Backend는 Step이 아닌 StrEnum이며 pipeworks와 pipeworks.embedded에서 가져올 수 있습니다.

| 상수 | 문자열 값 | 모델 형식 |
| --- | --- | --- |
| Backend.TENSORRT | tensorrt | 직렬화 TensorRT 엔진 |
| Backend.TORCHSCRIPT | torchscript | torch.jit.save로 저장한 TorchScript |
| Backend.ULTRALYTICS | ultralytics | Ultralytics PyTorch .pt 체크포인트 |
| Backend.PATCHCORE | patchcore | ResNet18 기반 patchcore-v1 result.pt |

```python
from pathlib import Path
from pipeworks import Backend
from pipeworks.embedded import YoloInference

step = YoloInference(Path("models/model.pt"), backend=Backend.ULTRALYTICS)
```

위 상대경로는 실행 작업 디렉터리 기준이므로 실제 앱에서는 파일 기준 절대경로를 사용합니다. 확장자만으로 실행부를 자동 선택하지 않으며 일반 .pt 체크포인트를 TorchScript로 열 수 있다는 뜻이 아닙니다. YAML에서는 enum의 문자열 값을 사용합니다. 사용자 실행부는 enum에 항목을 추가하지 않고 모듈:클래스 문자열로 지정합니다.

[YoloInference](embedded/yolo_inference.md), [실행부 계약](yolo_backend.md), [내장 실행부](yolo_backends/README.md)를 참고하세요.
