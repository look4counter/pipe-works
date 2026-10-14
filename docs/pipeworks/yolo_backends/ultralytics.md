# UltralyticsBackend

구현: src/pipeworks/yolo_backends/ultralytics.py. 생성자는 UltralyticsBackend(model_path, gpu_id)이며 선택 시 ultralytics.nn.tasks.load_checkpoint를 가져와 .pt 체크포인트를 지정 CUDA GPU에 fuse=True로 로드합니다. 다른 확장자는 ValueError입니다.

infer(inputs)는 텐서 하나 또는 항목 하나인 입력 사전을 받습니다. 입력은 FP32/FP16, 4차원 BCHW, 채널 수 3이어야 합니다. 사전의 입력 이름은 모델의 키워드 인자로 사용하지 않고 유일한 텐서 값을 사용합니다. 입력 자료형이 바뀌면 모델 자료형도 변경하고 불변 stride 정보를 갱신합니다.

내부 PyTorch 모델을 직접 호출하고 결과를 반환합니다. AutoBackend·NumPy 변환·영상 정규화·NMS를 추가하지 않습니다. GPU 출력의 이름 평탄화·복제는 상위 YoloInference가 담당하며 주 감지 예측의 이름은 통상 output0입니다. 내보낸 모델의 실제 출력 계약에 맞는 후처리를 연결합니다. [YoloInference](../embedded/yolo_inference.md)를 참고하세요.
