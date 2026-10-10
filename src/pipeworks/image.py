"""Shared GPU image conversion without model-specific dependencies."""

import torch


def nv12_to_rgb(image: torch.Tensor) -> torch.Tensor:
    """Convert packed GPU uint8 NV12 to independent FP32 CHW RGB in [0, 1]."""
    if not image.is_cuda or image.dtype != torch.uint8 or image.ndim != 2:
        raise ValueError("NV12 입력은 GPU의 2차원 uint8 텐서여야 합니다.")
    packed_height, width = image.shape
    if packed_height % 3 or width % 2:
        raise ValueError("NV12 프레임 크기가 잘못되었습니다.")
    height = packed_height * 2 // 3
    y = image[:height].float()
    uv = image[height:].reshape(height // 2, width // 2, 2).float()
    u = uv[..., 0].repeat_interleave(2, 0).repeat_interleave(2, 1) - 128
    v = uv[..., 1].repeat_interleave(2, 0).repeat_interleave(2, 1) - 128
    c = (y - 16).clamp_min(0) / 219
    r = (c + 1.402 * v / 224).clamp(0, 1)
    g = (c - 0.344136 * u / 224 - 0.714136 * v / 224).clamp(0, 1)
    b = (c + 1.772 * u / 224).clamp(0, 1)
    return torch.stack((r, g, b))
