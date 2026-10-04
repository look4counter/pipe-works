"""Run synchronous YOLO inference at the configured frame interval."""

import logging
from pathlib import Path
import time
from types import SimpleNamespace
from typing import Iterator

import cv2
import torch

from pipeworks.embedded.stream_report import record_inference
from pipeworks.models import PipelineContext, Step


logger = logging.getLogger(__name__)


class YoloDetect(Step):
    def __init__(self, model_path: Path) -> None:
        self.model_path = model_path
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

    def process(self, inputs: Iterator[PipelineContext]) -> Iterator[PipelineContext]:
        model = None
        for frame_index, item in enumerate(inputs):
            item.detections = None
            if frame_index % self.inference_interval != 0:
                yield item
                continue
            try:
                pixel_format = getattr(item.pixel_format, "name", item.pixel_format)
                if str(pixel_format).upper() != "NV12":
                    raise ValueError(f"지원하지 않는 YOLO 입력 픽셀 형식: {pixel_format}")

                height = item.video_stream.codec_context.height
                width = item.video_stream.codec_context.width
                if height % 2 or width % 2:
                    raise ValueError("NV12 프레임의 너비와 높이는 짝수여야 합니다.")

                with torch.cuda.stream(item.cuda_stream):
                    frame = torch.from_dlpack(item.frame)
                    if frame.ndim == 1 and frame.numel() == height * width * 3 // 2:
                        frame = frame.reshape(height * 3 // 2, width)
                    if frame.ndim != 2 or frame.shape[0] < height * 3 // 2 or frame.shape[1] < width:
                        raise ValueError(f"NV12 프레임 크기가 잘못되었습니다: {tuple(frame.shape)}")
                    item.cuda_stream.synchronize()
                    nv12 = frame[: height * 3 // 2, :width].cpu().numpy()

                image = cv2.cvtColor(nv12, cv2.COLOR_YUV2BGR_NV12)
                if model is None:
                    from ultralytics import YOLO

                    model = YOLO(str(self.model_path))
                started_at = time.perf_counter()
                results = model.predict(
                    image,
                    classes=self.classes,
                    conf=self.confidence,
                    device=self.gpu_id,
                    verbose=False,
                )
                completion_event = torch.cuda.Event()
                completion_event.record(torch.cuda.current_stream(self.gpu_id))
                completion_event.synchronize()
                record_inference(time.perf_counter() - started_at)
                item.detections = results[0].cpu()
            except Exception:
                logger.exception("YOLO 단일 감지에 실패하여 원본 프레임을 전달합니다.")
            yield item
