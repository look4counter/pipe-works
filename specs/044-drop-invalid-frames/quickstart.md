# 검증 절차

저장소 루트에서 기존 가상환경을 사용한다. CUDA가 없는 환경에서는 GPU 테스트가 생략된다.

```powershell
$env:PYTHONPATH='src;examples'
.venv/Scripts/python.exe -m unittest discover -s tests -p test_invalid_frame_drop.py -v
.venv/Scripts/python.exe -m unittest discover -s tests -p test_box_overlay.py -v
.venv/Scripts/python.exe -m unittest discover -s tests -p test_yolo_processing.py -v
.venv/Scripts/python.exe -m unittest discover -s tests -p test_async.py -v
.venv/Scripts/python.exe -m unittest discover -s tests -p test_every_n_frames.py -v
```

정상·비정상·정상 입력에서는 정상 두 프레임만 출력하고 원본 크기를 바꾸지 않아야 한다. 비동기·주기 실행에서도 후속 단계가 비정상 프레임을 받지 않아야 한다. 크기 이외 오류와 기존 정상 동작 검증은 통과해야 한다.

## 실행 결과

2026-10-19, 기존 CUDA 가상환경에서 신규 폐기 테스트 6개를 포함해 관련 테스트 144개가 통과했다. 추가 검증 범위에는 디코더 버퍼 수명, 프레임 해제, 모델 ID별 박스 표시와 TensorRT 처리도 포함했다.

기존 실패 3건은 변경 전 HEAD의 해당 모듈을 메모리에 로드해서 같은 오류가 재현됨을 확인했고, 통합 회귀 실행에서는 제외했다.

- `test_box_overlay.BoxOverlayTests.test_example_places_configured_overlay_before_encoder`: 예제의 EveryNFrames 내부 추론 단계를 찾지 못해 StopIteration이 발생한다.
- `test_async.AsyncTests.test_remote_registration_visits_inner_user_step`: 원격 실행 테스트 입력에 batch_server가 없어 AttributeError가 발생한다.
- `test_async.AsyncTests.test_remote_serializes_all_nested_user_steps_without_modules`: 같은 batch_server 누락으로 AttributeError가 발생한다.

이번 기능 범위를 벗어나는 위 테스트와 예제 구조는 수정하지 않았다.
