# 동기 감지 검증 안내

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -p test_yolo_detect.py -v
.venv/Scripts/python.exe -m unittest discover -s tests -p test_tensor_rt_inference.py -v
.venv/Scripts/python.exe -m unittest discover -s tests -p test_async.py -v
```

이벤트로 초기화·추론을 막아 해제 전 결과가 반환되지 않는지 확인한다. GPU 크기·좌표·CPU 복사 금지와 호출 문맥의 통계를 검증한다. 공통 Async로 감싸면 지연·오류 원본 통과가 적용되어야 한다. TensorRT 기존 시간 제한 테스트도 통과해야 한다. 실제 모델 또는 CUDA가 없는 검증은 조건부로 건너뛴다.

## 2026-10-09 검증 결과

- 단일 감지 14개 실행: 통과, 실제 YOLO 엔진 부재로 1개 건너뜀. 실제 `.pt` 모델, 호출 스레드·초기화와 추론 대기·오류 전파·입력 검증·GPU 좌표·통계·Async 조합을 확인했다.
- TensorRT 12개 실행: 모두 통과. 실제 원시 GPU 엔진과 기존 지연·오류 통과 동작을 유지했다.
- Async 19개, 공유 GPU 추론 6개, 배치 감지 16개 실행: 실패 없음. 공유 GPU 추론의 YOLO 엔진 검증 1건을 파일 부재로 건너뛰었다.
- 전체 회귀: 156개 실행, 오류 1개·건너뜀 3개. 이전 실행에서 실패했던 중앙 서버 종료 검증은 이번에는 통과했다.
- 전체 오류는 `test_example_places_configured_overlay_before_encoder`의 기존 예제 기대 불일치이다. 테스트는 `YoloDetectBatch`를 기대하지만 현재 예제는 `YoloDetect`를 사용한다. 이번 작업에서는 예제와 이 테스트를 변경하지 않았다.
- 전체 검증은 Windows 명명된 파이프 접근을 위해 기존 승인 범위에서 샌드박스 밖에서 실행했다.
- `git diff --check` 통과. 현재 요구사항 11개·성공 기준 5개와 구현을 대조하여 남은 미구현 항목이 없음을 확인했다.
