# 데이터 모델

체크포인트: format=patchcore-v1, backbone=resnet18, 양의 정수 imgsz,
state_dict, threshold, metadata, preprocessing을 저장한다.
state_dict는 비어 있지 않은 유한한 float32 memory_bank [N,384],
mean/std와 ResNet18 가중치를 포함한다. 누락·불일치는 로딩 오류이다.
threshold는 null 또는 유한한 숫자, metadata는 사전이다.
입력은 지정 GPU의 float32 [B,3,H,W] RGB 0~1, 모든 축은 양수이다.
출력은 같은 GPU의 pred_score [B], anomaly_map [B,H,W]이다.
상태는 파일 로드 → 검증 → 복원 → 지정 GPU 배치 → 반복 추론이다.
