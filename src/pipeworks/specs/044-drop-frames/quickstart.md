# 사용 및 검증

```python
from pipeworks.embedded import DropFrames, NvidiaEncode

# 30fps 입력의 추론 앞에 배치하고, 인코더는 선택 후 FPS로 설정한다.
selector = DropFrames(keep_every=2)
encoder = NvidiaEncode(fps=15)
```

파이프라인 순서는 디코더 → DropFrames → 추론 → 인코더이다.
이 Step은 기존 시간 정보를 수정하지 않으며 인코더 설정을 자동으로 변경하지 않는다.

현재 디렉터리에서 검증:

```powershell
$env:PYTHONPATH = (Resolve-Path ..).Path
& ../../.venv/Scripts/python.exe -m unittest discover -s specs/044-drop-frames -p 'test_*.py'
```

검증은 GPU 없이 프레임 선택, 설정 오류, 재사용 및 메타데이터 보존을 확인한다.
