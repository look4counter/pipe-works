# 검증 안내

YOLO 감지 또는 CudaAsync 뒤에 `.step(YoloDetectReport())`를 추가한다. TensorRT 전처리·추론·후처리 또는 해당 CudaAsync 뒤에 `.step(TensorRTReport())`를 추가한다.

`.venv/Scripts/python.exe -m unittest discover -s tests -p test_detection_report.py`로 통계를 검증한다. 관련 YOLO·TensorRT·비동기 테스트를 실행한 후 실제 스트림에서 전처리, 모델 실행, NMS, 대기·복사를 비교한다. GPU 이벤트를 읽기 위한 동기화가 추가되지 않아야 한다.
