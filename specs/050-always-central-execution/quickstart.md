# 검증 안내

저장소 루트에서 .venv의 Python 3.11 및 GPU 의존성을 사용한다.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_pipeline_routing.py -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_inference_contract.py -v
```

경로 검증은 배치 여부와 관계없이 중앙 실행을 요청하고, 개별 추론 계약 검증은 공유 배치 함수를 호출하지 않아야 한다. 실제 중앙 서버 검증은 Named Pipe 생성이 허용된 Windows 환경에서 tests/test_central_process.py의 관련 시나리오를 실행한다.

## 2026-11-06 실행 결과

- tests/test_pipeline_routing.py: 5개 통과. 배치 참·거짓의 래퍼 조합, 빈 단계, 서버 내부 실행, 실패 전달을 확인했다.
- tests/test_central_process.py의 test_batch_server_constructor_contract: 1개 통과. 별칭 검증·기본값·직렬화 보존을 확인했다. 파일 문법 검사도 통과했다.
- tests/test_inference_contract.py: 실제 GPU 검증을 포함한 10개 통과. batch=False의 공유 배치 미호출과 batch=True의 개별 세션 미생성을 명시적으로 검증했다.
- tests/test_yolo_inference.py: 실제 GPU 검증을 포함한 27개 통과.
- 합계: 43개 통과. 중앙 프로세스 종단 간 실행의 성공을 의미하지 않는다.
- 별도 central-routing 서버 별칭으로 추론 없는 파이프라인의 실제 중앙 실행을 시도했지만, main.serve의 Listener.accept → CreateNamedPipe에서 PermissionError: WinError 5가 발생했다. Named Pipe 생성이 허용된 환경에서 종단 간 재검증이 필요하다. 이 시도의 테스트 서버는 종료됐다.
