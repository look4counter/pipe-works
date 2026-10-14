# TorchScriptBackend

구현: src/pipeworks/yolo_backends/torchscript.py. 생성자는 TorchScriptBackend(model_path, gpu_id)이며 torch.jit.load로 지정 CUDA 장치에 로드하고 eval을 적용합니다. 모델 parameter와 buffer가 같은 GPU인지 검증하고 그래프의 GPU 스칼라 상수를 메타데이터로 수집합니다.

infer(inputs)는 텐서를 위치 인자로 model(inputs), 사전을 이름 있는 인자로 model(**inputs)에 전달합니다. 모델 출력은 바꾸지 않고 반환하며 GPU 감시·출력 평탄화·복제·동기화는 상위 YoloInference가 담당합니다. 직접 생성하면 이 상위 계약을 자동으로 얻지 못합니다.

일반 체크포인트 .pt와 확장자만으로 구분할 수 없으므로 TorchScript로 내보낸 모델을 사용합니다. 리사이즈·정규화·NMS·CPU 대체는 제공하지 않습니다. [실행부 계약](../yolo_backend.md)을 참고하세요.
