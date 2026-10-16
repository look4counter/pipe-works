
from step.yolo_pre_process import YoloPreProcess, F
from pipeworks.models import Step


class TensorRTPreProcess(Step):
    _report_kind = "TensorRT"

    __init__ = YoloPreProcess.__init__
    configure = YoloPreProcess.configure
    _constant = YoloPreProcess._constant
    _read_frame = YoloPreProcess._read_frame
    _pixels = YoloPreProcess._pixels
    _resize = YoloPreProcess._resize
    _normalize = YoloPreProcess._normalize
    process = YoloPreProcess.process
