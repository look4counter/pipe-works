
from enum import StrEnum


class Backend(StrEnum):
    TENSORRT = "tensorrt"
    TORCHSCRIPT = "torchscript"
    ULTRALYTICS = "ultralytics"
    PATCHCORE = "patchcore"
