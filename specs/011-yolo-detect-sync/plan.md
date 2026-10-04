# 구현 계획: 동기식 YOLO 감지

**기준**: [명세](spec.md)

## 현재 구성

`YoloDetect.configure()`는 클래스 필터, 신뢰도, GPU 번호와 추론 간격을 검증한다. `process()`는 입력 순번으로 선택 프레임을 결정하고, 선택 프레임의 CUDA NV12를 CPU BGR로 변환한다. 같은 처리 구간의 모델 인스턴스를 재사용하고 결과를 원래 컨텍스트에 기록한다.

입력 변환이나 추론이 실패하면 해당 프레임은 `detections=None`으로 전달한다. 추론 호출의 시간은 `stream_report.record_inference()`에 기록한다. 설정, 간격, 오류 복구, 실제 모델 경로와 보고를 `tests/test_yolo_detect.py`에서 확인한다.
