# 내장 GPU 모델 실행부

src/pipeworks/yolo_backends는 YoloInference가 선택하는 실행 구현입니다. Step이 아니며 일반 앱은 해당 클래스를 직접 생성하지 않고 Backend를 지정합니다. 패키지 __init__.py에는 별도의 편의 API가 없습니다.

| backend | 구현과 문서 | 핵심 계약 |
| --- | --- | --- |
| torchscript | [torchscript.py](torchscript.md) | TorchScript 파일, 텐서 또는 이름별 입력 |
| ultralytics | [ultralytics.py](ultralytics.md) | .pt 체크포인트, 단일 BCHW 이미지 |
| tensorrt | [tensorrt.py](tensorrt.md) | 엔진의 실제 입출력 이름·자료형·프로파일 |
| patchcore | [patchcore.py](patchcore.md) | patchcore-v1, RGB float32 BCHW, 이상 점수·맵 |

[YoloBackend 확장](../yolo_backend.md), [Backend enum](../backend.md), [YoloInference](../embedded/yolo_inference.md)를 참고하세요. 영상 디코딩·색상 변환과 후처리는 호출자가 제공합니다. PatchCore의 resize·정규화는 학습 계약에 따라 모델 내부에서 수행합니다.
