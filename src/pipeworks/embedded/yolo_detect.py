"""Run bounded asynchronous YOLO inference without CPU image copies."""

import logging
import math
from contextvars import Context, copy_context
from dataclasses import dataclass, field
from queue import Empty, Queue
from threading import Event, Lock, Thread
from pathlib import Path
import time
from types import SimpleNamespace
from typing import Iterator

import torch
import yaml

from pipeworks.embedded.stream_report import record_inference
from pipeworks.models import PipelineContext, Step
from pipeworks.local_yolo import _GpuDetectionPredictor, _INPUT_SIZE, _nv12_to_rgb, _prepare_image


logger = logging.getLogger(__name__)



@dataclass
class _AsyncRequest:
    image: torch.Tensor | None
    ready_event: torch.cuda.Event
    source_owner: object
    source_tensor: torch.Tensor | None
    classes: list[int] | None
    confidence: float
    gpu_id: int
    submitted_at: float
    context: Context = field(default_factory=copy_context)
    done: Event = field(default_factory=Event)
    expired: Event = field(default_factory=Event)
    result: object = None
    completed_at: float | None = None


def _predict(model, request: _AsyncRequest, stream):
    rgb = _nv12_to_rgb(request.image)
    height, width = rgb.shape[-2:]
    image = _prepare_image(rgb).unsqueeze(0)
    started_at = time.perf_counter()
    try:
        results = model.predict(
            image, predictor=_GpuDetectionPredictor.type(),
            classes=request.classes, conf=request.confidence, device=request.gpu_id,
            verbose=False, imgsz=_INPUT_SIZE,
            save=False, show=False, save_txt=False, save_crop=False,
        )
    finally:
        prediction_event = torch.cuda.Event()
        prediction_event.record(stream)
        prediction_event.synchronize()
        request.context.run(record_inference, time.perf_counter() - started_at)

    from ultralytics.utils import ops

    result = results[0]
    if result.boxes.data.device != request.image.device:
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


class _AsyncWorker:
    def __init__(self, model_path: Path):
        self.model_path = model_path
        self.requests: Queue[_AsyncRequest] = Queue(maxsize=1)
        self.lock = Lock()
        self.stopped = Event()
        self.busy = False
        self.current: _AsyncRequest | None = None
        self.thread = Thread(target=self._run, name=f"pipeworks-yolo-async-{model_path.stem}", daemon=True)
        self.thread.start()

    def reserve(self):
        with self.lock:
            if self.stopped.is_set() or self.busy:
                return False
            self.busy = True
            return True

    def release(self):
        with self.lock:
            self.busy = False

    def submit(self, request):
        with self.lock:
            self.current = request
            self.requests.put_nowait(request)

    def close(self):
        self.stopped.set()

    def _run(self):
        model = None
        stream = None
        gpu_id = None
        while True:
            try:
                request = self.requests.get(timeout=0.05)
            except Empty:
                if self.stopped.is_set():
                    return
                continue
            try:
                if not self.stopped.is_set():
                    if gpu_id != request.gpu_id:
                        gpu_id = request.gpu_id
                        stream = torch.cuda.Stream(device=gpu_id)
                        model = None
                    with torch.cuda.stream(stream):
                        stream.wait_event(request.ready_event)
                        request.image.record_stream(stream)
                        if model is None:
                            from ultralytics import YOLO

                            model = YOLO(str(self.model_path))
                        request.result = _predict(model, request, stream)
            except Exception:
                logger.exception("YOLO 비동기 감지에 실패하여 원본 프레임을 전달합니다.")
                # 실패 전에 제출한 GPU 연산도 입력 소유권 해제 전에 완료한다.
                if stream is not None:
                    try:
                        stream.synchronize()
                    except Exception:
                        logger.exception("YOLO 작업자 CUDA 정리에 실패했습니다.")
            finally:
                # 종료 신호가 먼저 도착한 요청도 GPU 복제 완료까지 원본을 보관한다.
                try:
                    request.ready_event.synchronize()
                except Exception:
                    logger.exception("YOLO 입력 복제 정리에 실패했습니다.")
                request.image = None
                request.source_tensor = None
                request.source_owner = None
                request.ready_event = None
                with self.lock:
                    if request.expired.is_set() or self.stopped.is_set():
                        request.result = None
                    request.completed_at = time.monotonic()
                    self.current = None
                    self.busy = False
                    request.done.set()
                request = None
            if self.stopped.is_set():
                return

class YoloDetect(Step):
    def __init__(self, model_path: Path) -> None:
        self.model_path = model_path
        self.classes: list[int] | None = None
        self.confidence = 0.25
        self.gpu_id = 0
        self.inference_interval = 1
        self._worker: _AsyncWorker | None = None

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

    def _timeout_seconds(self):
        config_path = self.model_path.with_suffix(".yml")
        if not config_path.is_file():
            return 0.005
        try:
            with config_path.open(encoding="utf-8") as config_file:
                config = yaml.safe_load(config_file)
        except yaml.YAMLError as error:
            raise ValueError(f"YOLO 제한 시간 설정이 잘못되었습니다: {config_path}") from error
        if not isinstance(config, dict):
            raise ValueError(f"YOLO 제한 시간 설정은 객체여야 합니다: {config_path}")
        timeout = config.get("timeout", 5)
        if (isinstance(timeout, bool) or not isinstance(timeout, (int, float))
                or not math.isfinite(timeout) or timeout < 0):
            raise ValueError("timeout은 유한한 0 이상의 밀리초여야 합니다.")
        return timeout / 1000

    def _copy_frame(self, item):
        pixel_format = getattr(item.pixel_format, "name", item.pixel_format)
        if str(pixel_format).upper() != "NV12":
            raise ValueError(f"지원하지 않는 YOLO 입력 픽셀 형식: {pixel_format}")
        height = item.video_stream.codec_context.height
        width = item.video_stream.codec_context.width
        if height <= 0 or width <= 0 or height % 2 or width % 2:
            raise ValueError("NV12 프레임의 너비와 높이는 양의 짝수여야 합니다.")
        with torch.cuda.stream(item.cuda_stream):
            frame = torch.from_dlpack(item.frame)
            if not frame.is_cuda or frame.dtype != torch.uint8:
                raise ValueError("YOLO 입력은 GPU의 uint8 NV12 텐서여야 합니다.")
            if frame.device.index != self.gpu_id or item.cuda_stream.device.index != self.gpu_id:
                raise ValueError("YOLO 입력 및 CUDA 스트림의 GPU는 gpu_id와 일치해야 합니다.")
            if frame.ndim == 1 and frame.numel() == height * width * 3 // 2:
                frame = frame.reshape(height * 3 // 2, width)
            if frame.ndim != 2 or frame.shape[0] < height * 3 // 2 or frame.shape[1] < width:
                raise ValueError(f"NV12 프레임 크기가 잘못되었습니다: {tuple(frame.shape)}")
            image = frame[: height * 3 // 2, :width].clone()
            ready_event = torch.cuda.Event()
            ready_event.record(item.cuda_stream)
        return image, ready_event, frame

    def process(self, inputs: Iterator[PipelineContext]) -> Iterator[PipelineContext]:
        timeout = self._timeout_seconds()
        worker = None
        try:
            for frame_index, item in enumerate(inputs):
                item.detections = None
                if frame_index % self.inference_interval == 0:
                    if self._worker is None or not self._worker.thread.is_alive():
                        self._worker = _AsyncWorker(self.model_path)
                    worker = self._worker
                    if worker.reserve():
                        submitted = False
                        request = None
                        try:
                            submitted_at = time.monotonic()
                            image, ready_event, source_tensor = self._copy_frame(item)
                            request = _AsyncRequest(
                                image, ready_event, item.frame, source_tensor,
                                list(self.classes) if self.classes is not None else None,
                                self.confidence, self.gpu_id, submitted_at,
                            )
                            worker.submit(request)
                            submitted = True
                            image = source_tensor = ready_event = None
                            deadline = submitted_at + timeout
                            ready = request.done.wait(max(0.0, deadline - time.monotonic()))
                            if ready and request.completed_at <= deadline:
                                item.detections = request.result
                            else:
                                request.expired.set()
                                request.result = None
                        except Exception:
                            if request is not None:
                                request.expired.set()
                            logger.exception("YOLO 요청에 실패하여 원본 프레임을 전달합니다.")
                        finally:
                            if not submitted:
                                worker.release()
                yield item
        finally:
            if worker is not None:
                worker.close()
