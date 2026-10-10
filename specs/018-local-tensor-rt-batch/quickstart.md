# 사용과 검증

## 모델 경로 초기화 시 검사 검증 (2026-10-10)

`.venv/Scripts/python.exe -m unittest discover -s tests -p test_model_worker.py`로 경로 조회 생략·파일 삭제·별칭 공유·CWD 구분·초기 누락·생성 실패 재시도·동시 최초 생성·레지스트리 재준비를 검증한다. 7개 모두 통과했다. 같은 명령의 패턴을 test_local_yolo.py, test_local_tensor_rt.py, test_yolo_batch.py, test_yolo_detect.py, test_tensor_rt_inference.py로 바꿔 GPU 공유 경로와 관련 회귀를 확인한다. 각각 10개(1개 건너뜀), 5개, 15개, 23개(1개 건너뜀), 24개가 완료되었다. 총 84개 중 82개 통과·2개 건너뜀이다. 파일 삭제 후 재사용은 resolve/is_file을 금지한 상태에서 검증했다. TensorRT 오류 후 파일 없는 재로드는 실패하고 파일 복구 후 성공했다. 실제 CUDA와 모의 모델·세션을 사용했으며 새 실제 모델 성능 측정이나 전체 테스트 모음 재실행은 하지 않았다.

FR-005~007, SC-002와 계획·작업을 현재 코드에 대조한 수렴 점검에서 남은 구현 작업은 없다. git diff --check도 통과했다. 기존 작업자에서 같은 입력 경로는 최초 해석 대상에 고정되며 실제 파일 읽기는 필요한 로드 시점에 유지된다.

`local_tensor_rt.infer(path, inputs, gpu_id=0, ready_event=event, on_inference_complete=callback)`은 배치 1 GPU 입력을 제출하고 GPU 출력 사전을 동기 반환한다. 입력을 다른 스트림에서 만들었다면 준비 이벤트를 반드시 전달한다. 입력은 완료까지 수정하지 않아야 한다. 모델 동명 YAML의 max_batch_size와 timeout은 최대 크기와 밀리초 수집 기한이며 자체 추론 제한은 없다. 입력과 출력은 축 0이 배치여야 한다.

TensorRTInference에는 아직 연결하지 않았다. 엔진이 수집되는 모든 배치 크기를 지원해야 하며 현재 고정 배치 1 예제는 max_batch_size=1로 사용한다. 작업자는 엔진 경로별로 공유하고 중앙 프로세스 수명 동안 유지한다.

명세·명확화·계획을 분석했고 차단 충돌은 없었다. 실제 CUDA 텐서와 모의 엔진으로 동시 요청 수집·출력 분리 및 잘못된 출력 이후 복구·설정 검증 3개가 통과했다. 이번 검증은 실제 배치 TensorRT 엔진 실행을 포함하지 않는다. 수렴 점검에서 추가 구현 차이는 없다.
