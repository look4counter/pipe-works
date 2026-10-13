# 검증 안내

1. batch=False 추론을 등록하고 Pipeline.run()을 실행하면 호출자에서 처리한다.
2. batch=True 추론을 등록하면 중앙 프로세스에서 처리한다.
3. CudaAsync와 EveryNFrames 등으로 감싸도 같은 기준을 적용한다.
4. .venv/Scripts/python.exe -m unittest discover -s tests -p test_pipeline_routing.py 명령으로 경로를 검증한다.

## 검증 결과

2026-10-14: 전체 unittest 424개 중 421개 통과, 기존 예제 관련 오류 3개. 변경 전 HEAD의 pipeline.py를 별도 Python 프로세스에서 메모리로 복원하여 예제 검사 8개를 실행했고 동일한 오류 3개를 재현했다. 파일은 변경하지 않았다.

- 새 라우팅 테스트 5개 통과: PID 유지, 직렬화 생략, 중첩·혼합 Batch, 반복 참조, 오류 전달.
- 중앙 프로토콜과 설정 감시 회귀 검증 통과.
- 실제 CUDA에서 TensorRT·TorchScript·Ultralytics 각각 두 요청을 묶은 Batch 2회, 세션 공유, GPU 출력과 보고서 검증 통과.
- 기존 오류: test_box_overlay의 중첩 추론 탐색 StopIteration 1개와 누락된 02_multiple_stream_rtsp_style.py 관련 FileNotFoundError 2개.
- git diff --check 통과.
