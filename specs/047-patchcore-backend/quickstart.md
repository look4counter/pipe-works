# 실행 검증

CUDA와 프로젝트 의존성을 준비한다. 모델은 yolo-trainer의 result.pt를 사용한다.
YoloInference의 backend에 Backend.PATCHCORE 또는 patchcore 문자열을 지정한다.
사용자가 RGB float32 BCHW 0~1 GPU 텐서를 model_input으로 제공한다.
model_output의 pred_score와 anomaly_map을 사용자 후처리에서 사용한다.
공유 배치는 batch=True와 모델 동명 yml의 max_batch_size·max_batch_wait_ms로 설정한다.
내부 정규화를 외부에서 중복 적용하지 않는다.

검증: `.venv/Scripts/python.exe -m unittest discover -s tests -p test_patchcore_backend.py -v`
기대 결과: 기준 구현 비교, 파일·입력 오류, GPU 및 공유 배치 검증 통과.
