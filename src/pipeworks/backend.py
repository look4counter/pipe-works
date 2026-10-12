"""Named model execution backends."""

from enum import StrEnum


class Backend(StrEnum):
    TENSORRT = "tensorrt"
    TORCHSCRIPT = "torchscript"
    ULTRALYTICS = "ultralytics"
