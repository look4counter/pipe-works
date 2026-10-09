"""Run synchronous GPU YOLO inference; compose with Async for bounded waiting."""

import logging
from pathlib import Path
import time
from types import SimpleNamespace
from typing import Iterator

import torch

from pipeworks.embedded.stream_report import record_inference
from pipeworks.models import PipelineContext, Step
from pipeworks.local_yolo import _GpuDetectionPredictor, _INPUT_SIZE, _nv12_to_rgb, _prepare_image


logger = logging.getLogger(__name__)


def _predict(model, image, classes, confidence, gpu_id, stream):
    rgb = _nv12_to_rgb(image)
    height, width = rgb.shape[-2:]
    prepared = _prepare_image(rgb).unsqueeze(0)
    started_at = time.perf_counter()
    try:
        results = model.predict(
            prepared, predictor=_GpuDetectionPredictor.type(),
            classes=classes, conf=confidence, device=gpu_id,
            verbose=False, imgsz=_INPUT_SIZE,
            save=False, show=False, save_txt=False, save_crop=False,
        )
    finally:
        prediction_event = torch.cuda.Event()
        prediction_event.record(stream)
        prediction_event.synchronize()
        record_inference(time.perf_counter() - started_at)

    from ultralytics.utils import ops

    result = results[0]
    if result.boxes.data.device != image.device:
        raise ValueError("YOLO 감지 결과는 입력과 같은 GPU에 있어야 합니다.")
    boxes = result.boxes.data.clone()
    boxes[:, :4] = ops.scale_boxes((_INPUT_SIZE, _INPUT_SIZE), boxes[:, :4], (height, width))
    result.orig_img = rgb.permute(1, 2, 0)
    result.orig_shape = (height, width)
    result.boxes.data = boxes
    result.boxes.orig_shape = result.orig_shape
    completion_event = torch.cuda.Event()
    completion_event.record(stream)
    completion_event.synchronize()
    return result


class YoloDetect(Step):
    def __init__(self, model_path: Path) -> None:
        self.model_path = Path(model_path)
        self.classes: list[int] | None = None
        self.confidence = 0.25
        self.gpu_id = 0
        self.inference_interval = 1

    def configure(self, config: SimpleNamespace) -> None:
        classes = getattr(config, "classes", None)
        confidence = getattr(config, "confidence", 0.25)
        gpu_id = getattr(config, "gpu_id", 0)
        inference_interval = getattr(config, "inference_interval", 1)
        if classes is not None and (
            not isinstance(classes, list)
            or any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in classes)
        ):
            raise ValueError("classes는 음수가 아닌 정수 목록이어야 합니다.")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 < confidence <= 1:
            raise ValueError("confidence는 0보다 크고 1 이하여야 합니다.")
        if isinstance(gpu_id, bool) or not isinstance(gpu_id, int) or gpu_id < 0:
            raise ValueError("gpu_id는 음수가 아닌 정수여야 합니다.")
        if isinstance(inference_interval, bool) or not isinstance(inference_interval, int) or inference_interval < 1:
            raise ValueError("inference_interval은 1 이상의 정수여야 합니다.")
        self.classes = classes
        self.confidence = confidence
        self.gpu_id = gpu_id
        self.inference_interval = inference_interval

    def _prepare_frame(self, item):
        pixel_format = getattr(item.pixel_format, "name", item.pixel_format)
        if str(pixel_format).upper() != "NV12":
            raise ValueError(f"지원하지 않는 YOLO 입력 픽셀 형식: {pixel_format}")
        height = item.video_stream.codec_context.height
        width = item.video_stream.codec_context.width
        if height <= 0 or width <= 0 or height % 2 or width % 2:
            raise ValueError("NV12 프레임의 너비와 높이는 양의 짝수여야 합니다.")
        frame = torch.from_dlpack(item.frame)
        if not frame.is_cuda or frame.dtype != torch.uint8:
            raise ValueError("YOLO 입력은 GPU의 uint8 NV12 텐서여야 합니다.")
        if frame.device.index != self.gpu_id or item.cuda_stream.device.index != self.gpu_id:
            raise ValueError("YOLO 입력 및 CUDA 스트림의 GPU는 gpu_id와 일치해야 합니다.")
        if frame.ndim == 1 and frame.numel() == height * width * 3 // 2:
            frame = frame.reshape(height * 3 // 2, width)
        if frame.ndim != 2 or frame.shape[0] < height * 3 // 2 or frame.shape[1] < width:
            raise ValueError(f"NV12 프레임 크기가 잘못되었습니다: {tuple(frame.shape)}")
        return frame[: height * 3 // 2, :width]

    def process(self, inputs: Iterator[PipelineContext]) -> Iterator[PipelineContext]:
        model = None
        model_gpu = None
        stream = None
        for frame_index, item in enumerate(inputs):
            item.detections = None
            if frame_index % self.inference_interval == 0:
                try:
                    with torch.cuda.stream(item.cuda_stream):
                        image = self._prepare_frame(item)
                        ready_event = torch.cuda.Event()
                        ready_event.record(item.cuda_stream)
                    if stream is None or stream.device.index != self.gpu_id:
                        stream = torch.cuda.Stream(device=self.gpu_id)
                    with torch.cuda.stream(stream):
                        stream.wait_event(ready_event)
                        image.record_stream(stream)
                        if model is None or model_gpu != self.gpu_id:
                            from ultralytics import YOLO

                            model = YOLO(str(self.model_path))
                            model_gpu = self.gpu_id
                        item.detections = _predict(
                            model, image, self.classes, self.confidence, self.gpu_id, stream,
                        )
                except Exception:
                    # Finish submitted CUDA work before releasing the original frame.
                    try:
                        if stream is not None:
                            stream.synchronize()
                        item.cuda_stream.synchronize()
                    except Exception:
                        logger.exception("YOLO 실패 후 CUDA 정리에 실패했습니다.")
                    raise
            yield item
