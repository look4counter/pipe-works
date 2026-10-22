# PatchCore 실행부

구현: src/pipeworks/yolo_backends/patchcore.py.
Backend.PATCHCORE 또는 문자열 patchcore로 선택합니다.
yolo-trainer가 저장한 ResNet18 기반 patchcore-v1의 result.pt를 지원합니다.
anomalib, 학습 프로젝트 패키지, 추가 가중치 다운로드가 필요하지 않습니다.
ResNet18 backbone 단독 가중치나 다른 형식의 .pt 파일은 지원하지 않습니다.

```python
from pathlib import Path
from pipeworks import Backend
from pipeworks.embedded import YoloInference

step = YoloInference(
    Path("models/result.pt").resolve(),
    backend=Backend.PATCHCORE,
    gpu_id=0,
)
```

## 입력

사용자는 지정 GPU에 RGB float32 [B,3,H,W] 텐서를 model_input으로 준비합니다.
값 범위는 0~1입니다. 사전 입력은 지원하지 않습니다.
입력의 정사각 resize와 ImageNet 정규화는 모델 내부에서 수행하므로 중복 적용하지 않습니다.
값 범위는 호출자가 보장하며 GPU 값을 CPU로 읽어 검사하지 않습니다.

## 출력

model_output은 다음 GPU 텐서 사전입니다.

| 키 | 형상 | 의미 |
| --- | --- | --- |
| pred_score | [B] | 클수록 이상인 원시 거리 점수 |
| anomaly_map | [B,H,W] | 입력 텐서 해상도의 원시 이상 맵 |

모델 내부 특징 맵의 최대 거리가 이미지 점수이며, 이상 맵은 입력 해상도로 보간합니다.
따라서 보간된 맵의 최대값과 이미지 점수가 반드시 같지는 않습니다.
체크포인트의 threshold와 metadata는 실행부 속성으로 보존합니다.
일반 Step 결과에는 점수와 맵만 전달합니다. 임계값 판정·맵 표시·원본 좌표 변환은
사용자 후처리가 담당합니다. 임계값은 학습 도구에서 정상 검증 점수의 99% 분위로 정합니다.

## 공유 배치

batch=True와 모델 동명 result.yml의 max_batch_size·max_batch_wait_ms로 설정합니다.
각 요청의 첫 축은 1이어야 하며 결과도 첫 축 1을 유지해 분리됩니다.
GPU 전용 실행, 현재 CUDA 스트림, profile_index=0 등의 기존 계약을 따릅니다.
잘못된 형식·가중치·메모리 뱅크는 로딩 시, 잘못된 입력은 추론 시 거절합니다.
