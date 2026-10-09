"""TensorRT 감지 구간별 성능을 출력한다."""

from pipeworks.detection_profile import DetectionReport


class TensorRTReport(DetectionReport):
    kind = "TensorRT"
