from types import SimpleNamespace
from pipeworks.models import Step, PipelineContext
from typing import Iterator
import re
import torch


class BoxOverlay(Step):

    def configure(self, config: SimpleNamespace) -> None:
        self.line_width = getattr(config, "line_width", 2)
        self.line_color = getattr(config, "line_color", "#00ff00")
        self.keep_previous = getattr(config, "keep_previous", True)
        if isinstance(self.line_width, bool) or not isinstance(self.line_width, int) or self.line_width < 1:
            raise ValueError("line_width는 1 이상의 정수여야 합니다.")
        if not isinstance(self.line_color, str) or re.fullmatch(r"#[0-9a-fA-F]{6}", self.line_color) is None:
            raise ValueError("line_color는 #RRGGBB 형식이어야 합니다.")
        if not isinstance(self.keep_previous, bool):
            raise ValueError("keep_previous는 불리언이어야 합니다.")

        red, green, blue = (int(self.line_color[index:index + 2], 16) for index in (1, 3, 5))
        self.yuv_color = (
            round(16 + (65.481 * red + 128.553 * green + 24.966 * blue) / 255),
            round(128 + (-37.797 * red - 74.203 * green + 112 * blue) / 255),
            round(128 + (112 * red - 93.786 * green - 18.214 * blue) / 255),
        )

    def process(self, inputs: Iterator[PipelineContext]) -> Iterator[PipelineContext]:
        previous_boxes: list[list[float]] = []
        previous_size: tuple[int, int] | None = None
        for item in inputs:
            pixel_format = getattr(item.pixel_format, "name", item.pixel_format)
            if str(pixel_format).upper() != "NV12":
                raise ValueError(f"BoxOverlay는 NV12 프레임만 지원합니다: {pixel_format}")
            height = item.video_stream.codec_context.height
            width = item.video_stream.codec_context.width
            if height % 2 or width % 2:
                raise ValueError("NV12 프레임의 너비와 높이는 짝수여야 합니다.")
            if previous_size != (width, height):
                previous_boxes = []
                previous_size = (width, height)

            detections = getattr(item, "detections", None)
            if detections is not None:
                boxes = getattr(detections, "boxes", None)
                xyxy = getattr(boxes, "xyxy", None)
                previous_boxes = [] if xyxy is None else xyxy.detach().to("cpu").tolist()
                current_boxes = previous_boxes
            else:
                current_boxes = previous_boxes if self.keep_previous else []

            if current_boxes:
                with torch.cuda.stream(item.cuda_stream):
                    frame = torch.from_dlpack(item.frame)
                    if frame.ndim == 1 and frame.numel() == height * width * 3 // 2:
                        frame = frame.reshape(height * 3 // 2, width)
                    if (not frame.is_cuda or frame.dtype != torch.uint8 or frame.ndim != 2
                            or frame.shape[0] < height * 3 // 2 or frame.shape[1] < width):
                        raise ValueError("BoxOverlay는 GPU의 2차원 uint8 NV12 프레임이 필요합니다.")
                    y_plane = frame[:height, :width]
                    uv_plane = frame[height:height + height // 2, :width]
                    y_value, u_value, v_value = self.yuv_color

                    def paint(left: int, top: int, right: int, bottom: int) -> None:
                        y_plane[top:bottom, left:right] = y_value
                        chroma = uv_plane[top // 2:(bottom + 1) // 2,
                                          left // 2 * 2:(right + 1) // 2 * 2]
                        chroma[:, 0::2] = u_value
                        chroma[:, 1::2] = v_value

                    for coordinates in current_boxes:
                        left, top, right, bottom = (round(value) for value in coordinates)
                        if right < 0 or bottom < 0 or left >= width or top >= height or right < left or bottom < top:
                            continue
                        left = max(0, left)
                        top = max(0, top)
                        right = min(width - 1, right) + 1
                        bottom = min(height - 1, bottom) + 1
                        thickness = self.line_width
                        paint(left, top, right, min(bottom, top + thickness))
                        paint(left, max(top, bottom - thickness), right, bottom)
                        paint(left, top, min(right, left + thickness), bottom)
                        paint(max(left, right - thickness), top, right, bottom)
            yield item
