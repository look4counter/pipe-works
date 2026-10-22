# 실행부 계약

Backend.PATCHCORE의 값은 patchcore이다.
PatchCoreBackend(model_path, gpu_id)는 지정 GPU에서 체크포인트를 실행한다.
infer(inputs)는 단일 float32 RGB BCHW GPU 텐서를 받으며 사전은 거절한다.
pred_score [B], anomaly_map [B,H,W]를 반환하며 맵은 입력 해상도이다.
threshold·metadata는 속성으로 보존한다. 출력은 점수와 맵만 포함한다.
backbone 단독 가중치, anomalib 체크포인트, TorchScript는 지원하지 않는다.
입력 범위는 0~1이며 resize와 ImageNet 정규화는 모델이 수행한다.
