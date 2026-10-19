
import logging
import math
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Iterator

import torch
import torch.nn.functional as F

from pipeworks.embedded.yolo_report import span, use
from pipeworks.execution import release_frame, _DroppedFrame, _can_signal_frame_drop
from pipeworks.inference_contract import begin_preprocess
from pipeworks.models import PipelineContext, Step


logger = logging.getLogger(__name__)


class _InvalidNV12Size(ValueError):
    pass


@dataclass(frozen=True)
class ImageTransform:

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
        height, width = self.shape
        ratio_x, ratio_y = self.ratio_xy
        boxes[:, 0:4:2].sub_(self.left).div_(ratio_x).clamp_(0, width)
        boxes[:, 1:4:2].sub_(self.top).div_(ratio_y).clamp_(0, height)
        return boxes


def nv12_to_rgb(image: torch.Tensor) -> torch.Tensor:
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


def _number(value, name):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
    ):
        raise ValueError(f"{name}은 유한한 숫자여야 합니다.")
    return float(value)


def _size(value, name):
    if (
        not isinstance(value, (list, tuple))
        or len(value) != 2
        or any(isinstance(v, bool) or not isinstance(v, int) or v <= 0 for v in value)
    ):
        raise ValueError(f"{name}는 양의 정수 [높이, 너비]여야 합니다.")
    return tuple(value)


def _channels(value, name):
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(f"{name}는 채널별 숫자 3개여야 합니다.")
    return tuple(_number(v, name) for v in value)


class YoloPreProcess(Step):

    _report_kind = "YOLO"

    def __init__(
        self,
        *,
        size=(640, 640),
        resize_mode="letterbox",
        auto=False,
        stride=32,
        scaleup=True,
        center=True,
        padding_value=114,
        crop_size=None,
        color_order="rgb",
        scale=1 / 255,
        mean=(0, 0, 0),
        std=(1, 1, 1),
        dtype="float32",
        layout="nchw",
        input_name=None,
    ):
        self._set_config_defaults(
            size=size,
            resize_mode=resize_mode,
            auto=auto,
            stride=stride,
            scaleup=scaleup,
            center=center,
            padding_value=padding_value,
            crop_size=crop_size,
            color_order=color_order,
            scale=scale,
            mean=mean,
            std=std,
            dtype=dtype,
            layout=layout,
            input_name=input_name,
        )

    def configure(self, config: SimpleNamespace) -> None:
        config = vars(self._resolve_config(config))
        unknown = set(config) - set(self._config_defaults)
        if unknown:
            raise ValueError(f"알 수 없는 {type(self).__name__} 옵션: {sorted(unknown)}")
        config["size"] = _size(config["size"], "size")
        for name, choices in (
            ("resize_mode", ("letterbox", "stretch", "resize_center_crop")),
            ("color_order", ("rgb", "bgr")),
            ("dtype", ("float32", "float16")),
            ("layout", ("nchw", "nhwc")),
        ):
            if config[name] not in choices:
                raise ValueError(f"{name}은 {choices} 중 하나여야 합니다.")
        for name in ("auto", "scaleup", "center"):
            if not isinstance(config[name], bool):
                raise ValueError(f"{name}는 불리언이어야 합니다.")
        if (
            isinstance(config["stride"], bool)
            or not isinstance(config["stride"], int)
            or config["stride"] <= 0
        ):
            raise ValueError("stride는 양의 정수여야 합니다.")
        if config["auto"] and config["resize_mode"] != "letterbox":
            raise ValueError("auto=True는 letterbox에서만 사용할 수 있습니다.")
        if config["crop_size"] is not None:
            if config["resize_mode"] != "resize_center_crop":
                raise ValueError(
                    "crop_size는 resize_center_crop에서만 사용할 수 있습니다."
                )
            config["crop_size"] = _size(config["crop_size"], "crop_size")
            if any(
                crop > size for crop, size in zip(config["crop_size"], config["size"])
            ):
                raise ValueError("crop_size는 size보다 클 수 없습니다.")
        padding = config["padding_value"]
        if not isinstance(padding, (list, tuple)):
            padding = (padding,) * 3
        config["padding_value"] = _channels(padding, "padding_value")
        if any(v < 0 or v > 255 for v in config["padding_value"]):
            raise ValueError("padding_value는 0~255 범위여야 합니다.")
        config["scale"] = _number(config["scale"], "scale")
        config["mean"] = _channels(config["mean"], "mean")
        config["std"] = _channels(config["std"], "std")
        if any(v <= 0 for v in config["std"]):
            raise ValueError("std는 양수여야 합니다.")
        name = config["input_name"]
        if name is not None and (not isinstance(name, str) or not name.strip()):
            raise ValueError(
                "input_name은 null 또는 비어 있지 않은 문자열이어야 합니다."
            )
        self.__dict__.update(config)
        self._constant_cache = {}


    def _constant(self, pixels, name):
        key = (pixels.device, pixels.dtype, name)
        entry = self._constant_cache.get(key)
        if entry is None:
            value = pixels.new_tensor(getattr(self, name)).view(1, 3, 1, 1)
            # 상수는 이후 다른 CUDA 스트림에서 사용될 수 있다.
            if pixels.is_cuda:
                torch.cuda.current_stream(pixels.device).synchronize()
            self._constant_cache[key] = value
            return value
        return entry


    def _read_frame(self, item):
        frame = getattr(item, "frame", None)
        if not isinstance(frame, torch.Tensor):
            if not callable(getattr(frame, "__dlpack__", None)):
                raise ValueError("frame은 GPU uint8 이미지여야 합니다.")
            frame = torch.from_dlpack(frame)
        if not frame.is_cuda or frame.dtype != torch.uint8:
            raise ValueError("frame은 GPU uint8 이미지여야 합니다.")
        pixel_format = getattr(item, "pixel_format", None)
        pixel_format = str(getattr(pixel_format, "name", pixel_format)).upper()
        if pixel_format == "NV12":
            codec = getattr(getattr(item, "video_stream", None), "codec_context", None)
            height, width = getattr(codec, "height", 0), getattr(codec, "width", 0)
            if any(
                isinstance(v, bool) or not isinstance(v, int) or v <= 0 or v % 2
                for v in (height, width)
            ):
                raise _InvalidNV12Size("NV12 입력은 양의 짝수 높이·너비 정보가 필요합니다.")
            if frame.ndim == 1 and frame.numel() == height * width * 3 // 2:
                frame = frame.reshape(height * 3 // 2, width)
            if (
                frame.ndim != 2
                or frame.shape[0] < height * 3 // 2
                or frame.shape[1] < width
            ):
                raise _InvalidNV12Size("NV12 입력 크기가 잘못되었습니다.")
            frame = frame[: height * 3 // 2, :width]
        elif pixel_format in ("RGB", "BGR"):
            if frame.ndim != 3 or frame.shape[2] != 3 or min(frame.shape[:2]) <= 0:
                raise ValueError("RGB/BGR 입력은 HWC 3채널 이미지여야 합니다.")
        else:
            raise ValueError("pixel_format은 NV12, RGB 또는 BGR이어야 합니다.")
        return frame, pixel_format


    def _pixels(self, frame, pixel_format):
        if pixel_format == "NV12":
            pixels = nv12_to_rgb(frame).mul_(255)
            source_order = "rgb"
        else:
            # 자료형 변환은 프레임과 독립된 저장 공간을 할당한다.
            pixels = frame.permute(2, 0, 1).float()
            source_order = pixel_format.lower()
        if source_order != self.color_order:
            pixels = pixels.flip(0)
        return pixels


    def _resize(self, pixels):
        height, width = pixels.shape[-2:]
        target_h, target_w = self.size
        left = top = 0
        if self.resize_mode == "stretch":
            resized_h, resized_w = self.size
            ratio_xy = (target_w / width, target_h / height)
        else:
            ratio = (min if self.resize_mode == "letterbox" else max)(
                target_h / height, target_w / width
            )
            if self.resize_mode == "letterbox" and not self.scaleup:
                ratio = min(ratio, 1)
            resized_h, resized_w = (
                max(1, round(height * ratio)),
                max(1, round(width * ratio)),
            )
            ratio_xy = (ratio, ratio)
        output = pixels.unsqueeze(0)
        if (resized_h, resized_w) != (height, width):
            output = F.interpolate(
                output,
                size=(resized_h, resized_w),
                mode="bilinear",
                align_corners=False,
            )
        if self.resize_mode == "letterbox":
            pad_h, pad_w = target_h - resized_h, target_w - resized_w
            if self.auto:
                pad_h, pad_w = pad_h % self.stride, pad_w % self.stride
            top, left = (pad_h // 2, pad_w // 2) if self.center else (0, 0)
            if pad_h or pad_w:
                padding = self._constant(output, "padding_value")
                padded = output.new_empty((1, 3, resized_h + pad_h, resized_w + pad_w))
                padded.copy_(padding)
                padded[:, :, top : top + resized_h, left : left + resized_w] = output
                output = padded
        elif self.resize_mode == "resize_center_crop":
            crop_h, crop_w = self.crop_size or self.size
            top, left = -((resized_h - crop_h) // 2), -((resized_w - crop_w) // 2)
            output = output[:, :, -top : -top + crop_h, -left : -left + crop_w]
        transform = ImageTransform(
            shape=(height, width),
            ratio_xy=ratio_xy,
            left=left,
            top=top,
            output_shape=tuple(output.shape[-2:]),
            resize_mode=self.resize_mode,
        )
        return output, transform


    def _normalize(self, pixels):
        # _pixels는 항상 소스 프레임과 독립된 저장 공간을 소유한다.
        # 유효 범위의 극단적인 설정값에서도 기존 연산 순서를 유지한다.
        output = pixels
        if self.scale != 1:
            output.mul_(self.scale)
        if any(value != 0 for value in self.mean):
            output.sub_(self._constant(output, "mean"))
        if any(value != 1 for value in self.std):
            output.div_(self._constant(output, "std"))
        if self.layout == "nhwc":
            output = output.permute(0, 2, 3, 1)
        return output.to(dtype=getattr(torch, self.dtype)).contiguous()


    def process(self, inputs: Iterator[PipelineContext]) -> Iterator[PipelineContext]:
        report_kind = self._report_kind
        for item in inputs:
            profile = begin_preprocess(report_kind)
            if profile is not None:
                item._inference_profile = profile
            stream = None
            try:
                frame, pixel_format = self._read_frame(item)
                stream = getattr(item, "cuda_stream", None)
                if stream is None:
                    stream = torch.cuda.current_stream(frame.device)
                    item.cuda_stream = stream
                if stream.device != frame.device:
                    raise ValueError(
                        "입력 CUDA 스트림과 frame의 GPU가 일치해야 합니다."
                    )
                with (
                    use(profile),
                    span("preprocess", stream),
                    torch.cuda.stream(stream),
                    torch.no_grad(),
                ):
                    pixels = self._pixels(frame, pixel_format)
                    frame_done = torch.cuda.Event()
                    frame_done.record(stream)
                    release_frame(ready_event=frame_done)
                    resized, transform = self._resize(pixels)
                    output = self._normalize(resized)
                with use(profile), span("completion_wait"):
                    stream.synchronize()
                item.model_input = (
                    output if self.input_name is None else {self.input_name: output}
                )
                item.image_transform = transform
            except _InvalidNV12Size as error:
                logger.warning("NV12 크기 오류로 프레임을 폐기합니다: %s", error)
                if profile is not None:
                    profile.finish("error")
                vars(item).pop("_inference_profile", None)
                if _can_signal_frame_drop():
                    yield _DroppedFrame()
                continue
            except Exception:
                if stream is not None:
                    stream.synchronize()
                if profile is not None:
                    profile.finish("error")
                vars(item).pop("_inference_profile", None)
                raise
            del frame, pixels, resized, output
            yield item
