import logging
from datetime import datetime
import time
import torch

from pipeline.arguments import PipelineArguments
from pipeline.context import FrameContext

logger = logging.getLogger(__name__)

_GLYPHS = {
    "0": ("111", "101", "101", "101", "111"),
    "1": ("010", "110", "010", "010", "111"),
    "2": ("111", "001", "111", "100", "111"),
    "3": ("111", "001", "111", "001", "111"),
    "4": ("101", "101", "111", "001", "001"),
    "5": ("111", "100", "111", "001", "111"),
    "6": ("111", "100", "111", "101", "111"),
    "7": ("111", "001", "010", "010", "010"),
    "8": ("111", "101", "111", "101", "111"),
    "9": ("111", "101", "111", "001", "111"),
    "-": ("000", "000", "111", "000", "000"),
    ":": ("000", "010", "000", "010", "000"),
    " ": ("000", "000", "000", "000", "000"),
}

_DEFAULT_FONT_SIZE = 14
_DEFAULT_YUV = (150, 43, 21)
_last_inference_result: str | None = None


def _overlay_parameters(parameters: dict | None, frame: FrameContext) -> tuple[int, tuple[int, int, int]]:
    """Validate model parameters without letting a bad live edit drop a frame."""
    parameters = parameters if isinstance(parameters, dict) else {}
    font_size = frame.metadata.get("font-size", _DEFAULT_FONT_SIZE)
    try:
        scale = max(1, min(4, int(font_size) // 7))
    except (TypeError, ValueError):
        scale = max(1, font_size // 7)

    yuv = frame.metadata.get("font-color", _DEFAULT_YUV)
    if (
        not isinstance(yuv, (list, tuple))
        or len(yuv) != 3
        or any(not isinstance(value, int) or not 0 <= value <= 255 for value in yuv)
    ):
        yuv = _DEFAULT_YUV
    return scale, (yuv[0], yuv[1], yuv[2])


def _draw_timestamp_nv12(
    frame: FrameContext, timestamp: str, parameters: dict | None = None
) -> None:
    """Draw a timestamp on the NV12 luma plane without copying the frame to CPU."""
    if frame.pixel_format.upper() != "NV12":
        raise ValueError("The basic timestamp example requires NV12 input frames")

    nv12 = torch.from_dlpack(frame.data)
    if (
        nv12.ndim != 2
        or frame.height % 2
        or frame.width % 2
        or nv12.shape[0] < frame.height + frame.height // 2
        or nv12.shape[1] < frame.width
    ):
        raise ValueError("NV12 frame data must expose two-dimensional luma and chroma planes")

    glyph_width = 3
    glyph_spacing = 1
    margin = 8
    scale, (luma_value, chroma_u, chroma_v) = _overlay_parameters(parameters, frame)
    max_width_scale = max(1, (frame.width - 2 * margin) // (len(timestamp) * 4))
    max_height_scale = max(1, (frame.height - 2 * margin) // len(_GLYPHS["0"]))
    scale = min(scale, max_width_scale, max_height_scale)
    text_width = (
        len(timestamp) * (glyph_width + glyph_spacing) * scale - glyph_spacing * scale
    )
    x = max(margin, frame.width - margin - text_width)
    y = margin
    luma = nv12[: frame.height, : frame.width]

    for character in timestamp:
        for row, bits in enumerate(_GLYPHS[character]):
            for column, bit in enumerate(bits):
                if bit == "1":
                    y_start = y + row * scale
                    y_end = y + (row + 1) * scale
                    x_start = x + column * scale
                    x_end = x + (column + 1) * scale
                    luma[y_start:y_end, x_start:x_end] = luma_value

                    chroma_y_start = frame.height + y_start // 2
                    chroma_y_end = frame.height + (y_end + 1) // 2
                    chroma_x_start = (x_start // 2) * 2
                    chroma_x_end = ((x_end + 1) // 2) * 2
                    nv12[chroma_y_start:chroma_y_end, chroma_x_start:chroma_x_end:2] = chroma_u
                    nv12[chroma_y_start:chroma_y_end, chroma_x_start + 1:chroma_x_end:2] = chroma_v
        x += (glyph_width + glyph_spacing) * scale

    frame.data = nv12

def on_frame(infer: bool, parameters: PipelineArguments, frame: FrameContext) -> FrameContext:
    global _last_inference_result

    if infer or _last_inference_result is None:
        if infer:
            time.sleep(0.1)
        _last_inference_result = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    _draw_timestamp_nv12(frame, _last_inference_result, parameters)
    return frame
