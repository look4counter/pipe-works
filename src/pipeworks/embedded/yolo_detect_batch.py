from pathlib import Path
from types import SimpleNamespace
from typing import Iterator
import logging
import time

import torch

from pipeworks.models import PipelineContext, Step
from pipeworks.embedded.stream_report import record_inference, record_stage
from pipeworks.local_yolo import infer


logger = logging.getLogger(__name__)


class YoloDetectBatch(Step):
    def __init__(self, model_path: Path) -> None:
        self.model_path = model_path
        self.classes = None
        self.confidence = 0.25
        self.gpu_id = 0
        self.inference_interval = 1

    def configure(self, config: SimpleNamespace) -> None:
        self.classes = getattr(config, "classes", None)
        self.confidence = getattr(config, "confidence", 0.25)
        self.gpu_id = getattr(config, "gpu_id", 0)
        self.inference_interval = getattr(config, "inference_interval", 1)
        if hasattr(config, "low_latency"):
            raise ValueError("low_latency 설정은 더 이상 지원하지 않습니다.")
        if self.classes is not None and (
            not isinstance(self.classes, list)
            or any(not isinstance(value, int) or value < 0 for value in self.classes)
        ):
            raise ValueError("classes는 음수가 아닌 정수 목록이어야 합니다.")
        if not 0 < self.confidence <= 1:
            raise ValueError("confidence는 0보다 크고 1 이하여야 합니다.")
        if isinstance(self.inference_interval, bool) or not isinstance(self.inference_interval, int) or self.inference_interval < 1:
            raise ValueError("inference_interval은 1 이상의 정수여야 합니다.")

    def _copy_frame(self, item: PipelineContext):
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
            image = frame[: height * 3 // 2, :width].clone()
            ready_event = torch.cuda.Event()
            ready_event.record(item.cuda_stream)
        return image, ready_event

    def process(self, inputs: Iterator[PipelineContext]) -> Iterator[PipelineContext]:
        for frame_index, item in enumerate(inputs):
            dequeued_at = time.perf_counter()
            item.detections = None
            if frame_index % self.inference_interval == 0:
                try:
                    image, ready_event = self._copy_frame(item)
                    item.detections = infer(
                        self.model_path, image, self.classes, self.confidence, self.gpu_id,
                        ready_event=ready_event, on_inference_complete=record_inference,
                    )
                except Exception:
                    logger.exception("YOLO 감지에 실패하여 원본 프레임을 전달합니다.")
            emitted_at = time.perf_counter()
            record_stage("batch_queue", dequeued_at - getattr(item, "processing_started_at", dequeued_at))
            record_stage("batch_wait", emitted_at - dequeued_at)
            yield item
