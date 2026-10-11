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
        self.id = getattr(config, "id", None)
        if isinstance(self.line_width, bool) or not isinstance(self.line_width, int) or self.line_width < 1:
            raise ValueError("line_width는 1 이상의 정수여야 합니다.")
        if not isinstance(self.line_color, str) or re.fullmatch(r"#[0-9a-fA-F]{6}", self.line_color) is None:
            raise ValueError("line_color는 #RRGGBB 형식이어야 합니다.")
        if not isinstance(self.keep_previous, bool):
            raise ValueError("keep_previous는 불리언이어야 합니다.")
        if self.id is not None and (not isinstance(self.id, str) or not self.id.strip()):
            raise ValueError("id는 비어 있지 않은 문자열 또는 null이어야 합니다.")

        red, green, blue = (int(self.line_color[index:index + 2], 16) for index in (1, 3, 5))
        self.yuv_color = (
            round(16 + (65.481 * red + 128.553 * green + 24.966 * blue) / 255),
            round(128 + (-37.797 * red - 74.203 * green + 112 * blue) / 255),
            round(128 + (112 * red - 93.786 * green - 18.214 * blue) / 255),
        )

    @staticmethod
    def _mask(boxes, height, width, thickness):
        finite = torch.isfinite(boxes).all(dim=1)
        coords = torch.nan_to_num(boxes).round().to(torch.int64)
        left, top, right, bottom = coords.unbind(1)
        valid = finite & (right >= left) & (bottom >= top) & (right >= 0) & (bottom >= 0) & (left < width) & (top < height)
        left, top = left.clamp(0, width), top.clamp(0, height)
        right, bottom = right.clamp(0, width - 1) + 1, bottom.clamp(0, height - 1) + 1
        rects = torch.stack((
            torch.stack((left, top, right, torch.minimum(bottom, top + thickness)), 1),
            torch.stack((left, torch.maximum(top, bottom - thickness), right, bottom), 1),
            torch.stack((left, top, torch.minimum(right, left + thickness), bottom), 1),
            torch.stack((torch.maximum(left, right - thickness), top, right, bottom), 1),
        ), 1).reshape(-1, 4)
        x1, y1, x2, y2 = rects.unbind(1)
        indices = torch.stack((y1 * (width + 1) + x1, y1 * (width + 1) + x2,
                               y2 * (width + 1) + x1, y2 * (width + 1) + x2), 1)
        signs = torch.tensor([1, -1, -1, 1], dtype=torch.int32, device=boxes.device)
        values = valid[:, None].expand(-1, 4).reshape(-1, 1).to(torch.int32) * signs
        diff = torch.zeros((height + 1) * (width + 1), dtype=torch.int32, device=boxes.device)
        diff.scatter_add_(0, indices.reshape(-1), values.reshape(-1))
        return diff.reshape(height + 1, width + 1).cumsum(0, dtype=torch.int32).cumsum(1, dtype=torch.int32)[:height, :width] > 0

    def process(self, inputs: Iterator[PipelineContext]) -> Iterator[PipelineContext]:
        previous = {}
        previous_key = None
        for item in inputs:
            pixel_format = getattr(item.pixel_format, "name", item.pixel_format)
            if str(pixel_format).upper() != "NV12":
                raise ValueError("BoxOverlay requires NV12 input.")
            height = item.video_stream.codec_context.height
            width = item.video_stream.codec_context.width
            if height <= 0 or width <= 0 or height % 2 or width % 2:
                raise ValueError("NV12 dimensions must be positive and even.")
            stream = item.cuda_stream
            key = (width, height, stream.device, self.id)
            if previous_key != key:
                previous = {}
                previous_key = key
            with torch.cuda.stream(stream), torch.no_grad():
                detections = getattr(item, "detections", None)
                if isinstance(detections, dict):
                    selected = ({self.id: detections.get(self.id)} if self.id is not None
                                else {name: detections.get(name) for name in dict.fromkeys([*previous, *detections])})
                elif detections is None:
                    selected = {self.id: None} if self.id is not None else dict.fromkeys(previous)
                else:
                    # Preserve the single-result YOLO contract when no ID is selected.
                    selected = {self.id: detections if self.id is None else None}
                chosen = []
                for model_id, result in selected.items():
                    if result is not None:
                        xyxy = getattr(getattr(result, "boxes", None), "xyxy", None)
                        if xyxy is not None and (not isinstance(xyxy, torch.Tensor) or not xyxy.is_cuda
                                                  or xyxy.device != stream.device or xyxy.ndim != 2 or xyxy.shape[1] != 4):
                            raise ValueError("BoxOverlay boxes must be GPU Nx4 tensors on the frame device.")
                        if xyxy is None:
                            previous.pop(model_id, None)
                        else:
                            cached = xyxy.detach().clone()
                            ready = torch.cuda.Event()
                            ready.record(stream)
                            previous[model_id] = cached, ready
                    elif not self.keep_previous:
                        previous.pop(model_id, None)
                    if model_id in previous:
                        cached, ready = previous[model_id]
                        stream.wait_event(ready)
                        cached.record_stream(stream)
                        chosen.append(cached)
                boxes = (chosen[0] if len(chosen) == 1 else torch.cat(chosen)) if chosen else None
                if boxes is not None and boxes.shape[0]:
                    boxes.record_stream(stream)
                    frame = torch.from_dlpack(item.frame)
                    if frame.ndim == 1 and frame.numel() == height * width * 3 // 2:
                        frame = frame.reshape(height * 3 // 2, width)
                    if (not frame.is_cuda or frame.device != stream.device or frame.dtype != torch.uint8
                            or frame.ndim != 2 or frame.shape[0] < height * 3 // 2 or frame.shape[1] < width):
                        raise ValueError("BoxOverlay requires a GPU uint8 NV12 frame.")
                    mask = self._mask(boxes, height, width, self.line_width)
                    chroma = mask[0::2, 0::2] | mask[0::2, 1::2] | mask[1::2, 0::2] | mask[1::2, 1::2]
                    y, u, v = self.yuv_color
                    frame[:height, :width].masked_fill_(mask, y)
                    frame[height:height + height // 2, :width:2].masked_fill_(chroma, u)
                    frame[height:height + height // 2, 1:width:2].masked_fill_(chroma, v)
                    # The input owns the storage until downstream GPU work finishes.
                    del frame
            yield item
