# 검증 방법

프로젝트 환경에서 `python -m unittest discover -s tests -p test_tensor_rt_preprocess*.py`를 실행한다.
CUDA 환경에서 `python tools/benchmark_preprocess.py`를 실행하여 동일 입력의 기존식과 최적화식 시간을 비교한다. CPU 비교는 수치 검증이며 GPU 성능을 증명하지 않는다.

## 실행 결과

2026-10-10, PyTorch 2.2.1+cu121, RTX 4070 Laptop GPU. 준비 20회 이후 1000회 평균. 1080p 입력에서 640×640 출력.

| 입력·설정 | 기존 GPU 시간 | 변경 GPU 시간 |
| --- | --- | --- |
| RGB 기본 | 0.357 ms | 0.190 ms |
| RGB 채널별 정규화 | 0.295 ms | 0.203 ms |
| RGB FP16 NHWC | 0.313 ms | 0.218 ms |
| NV12 기본 | 2.908 ms | 2.402 ms |
| NV12 채널별 정규화 | 3.075 ms | 2.577 ms |
| NV12 FP16 NHWC | 3.258 ms | 2.616 ms |

측정 범위는 픽셀 변환·리사이즈·정규화이며 전체 파이프라인과 단계별 완료 대기 비용은 포함하지 않는다. GPU 이벤트 시간에도 반복 호출 사이의 CPU 제출 공백이 포함될 수 있다. 장치 클럭과 측정 순서에 따른 변동이 있으며 보장 수치가 아니다. 기준 구현은 Git HEAD에서 읽으므로 커밋 이후에는 변경 전 리비전을 기준으로 측정 도구를 조정해야 한다.

전처리 테스트 14개와 프레임 해제 테스트 6개 통과. 기존 전처리 테스트 전체 실행은 저장소에 없는 `examples/step/tensor_rt_pre_process.py`를 가져오는 1개 테스트에서 실패한다. `test_tensor_rt_processing.py`도 같은 기존 참조 때문에 읽기에 실패한다. 기존 파일을 임의로 복구하지 않는다.
