"""Reuse example-owned detection postprocessing under the TensorRT step name."""

from step.yolo_post_process import YoloPostProcess
from pipeworks.models import Step


class TensorRTPostProcess(Step):
    __init__ = YoloPostProcess.__init__
    configure = YoloPostProcess.configure
    _prediction = YoloPostProcess._prediction
    _nms = YoloPostProcess._nms
    process = YoloPostProcess.process
