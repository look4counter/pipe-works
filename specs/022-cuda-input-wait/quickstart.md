# 검증 안내

CUDA 지원 가상환경에서 실행한다.

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -p test_tensor_rt_inference.py
.venv/Scripts/python.exe -m unittest discover -s tests -p test_local_tensor_rt.py
.venv/Scripts/python.exe -m unittest discover -s tests -p test_tensor_rt_processing.py
.venv/Scripts/python.exe -m unittest discover -s tests -p test_async.py
```

입력 이벤트의 CPU 대기를 금지한 상태에서 지연 GPU 입력 결과가 참조와 일치해야 한다. 같은 스트림·다른 스트림·배치를 검증한다. 실제 엔진은 지원 환경에서 실행한다. 테스트 시간은 전체 영상 성능 향상률이 아니다.

## 실행 결과

2026-10-10 RTX 4070 Laptop GPU에서 추론 28개(실제 TensorRT 엔진 포함), 공유 배치 6개, 전후처리 6개, CudaAsync 38개로 총 78개가 통과했다. 신규 지연 입력 회귀는 기존 코드에서 CPU 입력 대기 금지 위반으로 실패하고 변경 후 통과했다. 같은 스트림·다른 스트림의 비연속 입력 및 복수 생산 스트림 배치 결과를 검증했다. git diff --check도 통과했다.
