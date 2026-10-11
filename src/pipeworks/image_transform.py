"""Image geometry and in-place restoration of model-input pixel coordinates."""

from dataclasses import dataclass

import torch


@dataclass(frozen=True)
class ImageTransform:
    """Map original pixels to model pixels by per-axis scale and translation."""

    shape: tuple[int, int]
    ratio_xy: tuple[float, float]
    left: int
    top: int
    output_shape: tuple[int, int]
    resize_mode: str

    @property
    def ratio(self):
        x, y = self.ratio_xy
        return x if x == y else self.ratio_xy

    def restore_boxes_(self, boxes: torch.Tensor) -> torch.Tensor:
        """Restore N×4-or-more xyxy rows in-place, preserving additional columns."""
        height, width = self.shape
        ratio_x, ratio_y = self.ratio_xy
        boxes[:, 0:4:2].sub_(self.left).div_(ratio_x).clamp_(0, width)
        boxes[:, 1:4:2].sub_(self.top).div_(ratio_y).clamp_(0, height)
        return boxes
