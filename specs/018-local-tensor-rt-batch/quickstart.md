# 사용과 검증

`local_tensor_rt.infer(path, inputs, gpu_id=0, ready_event=event, on_inference_complete=callback)`은 배치 1 GPU 입력을 제출하고 GPU 출력 사전을 동기 반환한다. 입력을 다른 스트림에서 만들었다면 준비 이벤트를 반드시 전달한다. 입력은 완료까지 수정하지 않아야 한다. 모델 동명 YAML의 max_batch_size와 timeout은 최대 크기와 밀리초 수집 기한이며 자체 추론 제한은 없다. 입력과 출력은 축 0이 배치여야 한다.

TensorRTInference에는 아직 연결하지 않았다. 엔진이 수집되는 모든 배치 크기를 지원해야 하며 현재 고정 배치 1 예제는 max_batch_size=1로 사용한다. 작업자는 엔진 경로별로 공유하고 중앙 프로세스 수명 동안 유지한다.

명세·명확화·계획을 분석했고 차단 충돌은 없었다. 실제 CUDA 텐서와 모의 엔진으로 동시 요청 수집·출력 분리 및 잘못된 출력 이후 복구·설정 검증 3개가 통과했다. 이번 검증은 실제 배치 TensorRT 엔진 실행을 포함하지 않는다. 수렴 점검에서 추가 구현 차이는 없다.
