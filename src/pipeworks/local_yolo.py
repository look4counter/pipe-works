"""Run shared YOLO batches on GPU inside the central process."""

from collections import deque
from dataclasses import dataclass, field
import math
from pathlib import Path
from queue import Queue
from pipeworks.batch_collector import collect_batch
from threading import Event, Lock, Thread
import time

import torch
import torch.nn.functional as F
import yaml
from pipeworks.detection_profile import Profile, span, use


_workers: dict[Path, "_ModelWorker"] = {}
_workers_lock = Lock()
_INPUT_SIZE = 640


@dataclass
class _InferenceRequest:
    image: torch.Tensor | None
    classes: list[int] | None
    confidence: float
    gpu_id: int
    ready_event: torch.cuda.Event | None = None
    received_at: float = field(default_factory=time.monotonic)
    done: Event = field(default_factory=Event)
    response: tuple[str, object] | None = None
    completion_event: torch.cuda.Event | None = None
    inference_seconds: float | None = None
    profile_enabled: bool = False
    profile: object = None

    @property
    def options(self) -> tuple[tuple[int, ...] | None, float, int]:
        return (tuple(self.classes) if self.classes is not None else None, self.confidence, self.gpu_id)


def _batch_settings(model_path: Path) -> tuple[int, float]:
    config_path = model_path.with_suffix(".yml")
    if not config_path.is_file():
        return 1, 0.0
    with config_path.open(encoding="utf-8") as config_file:
        config = yaml.safe_load(config_file)
    if not isinstance(config, dict):
        raise ValueError(f"YOLO 배치 설정은 객체여야 합니다: {config_path}")
    size = config.get("max_batch_size")
    timeout = config.get("timeout")
    if isinstance(size, bool) or not isinstance(size, int) or size < 1:
        raise ValueError("max_batch_size는 1 이상의 정수여야 합니다.")
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout < 0:
        raise ValueError("timeout은 0 이상의 밀리초여야 합니다.")
    return size, timeout / 1000


def _nv12_to_rgb(image: torch.Tensor) -> torch.Tensor:
    if not image.is_cuda or image.dtype != torch.uint8 or image.ndim != 2:
        raise ValueError("YOLO 입력은 GPU의 2차원 uint8 NV12 텐서여야 합니다.")
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


def _as_rgb(image: torch.Tensor) -> torch.Tensor:
    """Accept independently prepared RGB or legacy packed NV12 inputs."""
    if image.is_cuda and image.dtype == torch.float32 and image.ndim == 3 and image.shape[0] == 3:
        return image
    return _nv12_to_rgb(image)


def _prepare_image(rgb: torch.Tensor) -> torch.Tensor:
    height, width = rgb.shape[-2:]
    ratio = min(_INPUT_SIZE / height, _INPUT_SIZE / width)
    resized_height = round(height * ratio)
    resized_width = round(width * ratio)
    resized = F.interpolate(rgb.unsqueeze(0), size=(resized_height, resized_width), mode="bilinear", align_corners=False)[0]
    top = (_INPUT_SIZE - resized_height) // 2
    bottom = _INPUT_SIZE - resized_height - top
    left = (_INPUT_SIZE - resized_width) // 2
    right = _INPUT_SIZE - resized_width - left
    return F.pad(resized, (left, right, top, bottom), value=114 / 255)


class _GpuDetectionPredictor:
    @staticmethod
    def type():
        from ultralytics.models.yolo.detect.predict import DetectionPredictor
        from ultralytics.utils import nms

        class Predictor(DetectionPredictor):
            def preprocess(self, im):
                with span("preprocess", torch.cuda.current_stream(self.device)):
                    return super().preprocess(im)

            def inference(self, im, *args, **kwargs):
                with span("inference", torch.cuda.current_stream(im.device)):
                    return super().inference(im, *args, **kwargs)

            def postprocess(self, preds, img, orig_imgs, **kwargs):
                with span("postprocess", torch.cuda.current_stream(img.device)):
                    boxes = nms.non_max_suppression(
                        preds, self.args.conf, kwargs.pop("iou", self.args.iou),
                        self.args.classes, self.args.agnostic_nms,
                        max_det=self.args.max_det,
                        nc=0 if self.args.task == "detect" else len(self.model.names),
                        end2end=getattr(self.model, "end2end", False),
                    )
                    return self.construct_results(boxes, img, orig_imgs.permute(0, 2, 3, 1))

        return Predictor


class _ModelWorker:
    def __init__(self, model_path: Path) -> None:
        self.model_path = model_path
        self.max_batch_size, self.timeout = _batch_settings(model_path)
        self.requests: Queue[_InferenceRequest] = Queue()
        Thread(target=self._run, name=f"pipeworks-yolo-{model_path.stem}", daemon=True).start()

    def _run(self) -> None:
        model = None
        deferred: deque[_InferenceRequest] = deque()
        while True:
            batch = collect_batch(self.requests, deferred, self.max_batch_size, self.timeout,
                                  key=lambda request: request.options, received_at=lambda request: request.received_at)
            dequeued_at = time.monotonic()
            profile = Profile("YOLO") if any(r.profile_enabled for r in batch) else None
            scope = use(profile)
            scope.__enter__()
            try:
                stream = torch.cuda.current_stream(batch[0].image.device)
                with span("input_wait"):
                    for request in batch:
                        if request.ready_event is not None:
                            request.ready_event.wait(torch.cuda.current_stream(request.image.device))
                if model is None:
                    from ultralytics import YOLO

                    with span("prepare"):
                        model = YOLO(str(self.model_path))
                with span("preprocess", stream):
                    originals = [_as_rgb(request.image) for request in batch]
                    prepared = [_prepare_image(rgb) for rgb in originals]
                with span("input_copy", stream):
                    images = torch.stack(prepared)
                first = batch[0]
                prediction_started_at = time.perf_counter()
                results = model.predict(
                    images, predictor=_GpuDetectionPredictor.type(),
                    classes=first.classes, conf=first.confidence,
                    device=first.gpu_id, verbose=False, imgsz=_INPUT_SIZE,
                )
                prediction_event = torch.cuda.Event()
                prediction_event.record(torch.cuda.current_stream(first.image.device))
                with span("completion_wait"):
                    prediction_event.synchronize()
                inference_seconds = time.perf_counter() - prediction_started_at
                for request in batch:
                    request.inference_seconds = inference_seconds
                if len(results) != len(batch):
                    raise RuntimeError("YOLO 배치 결과 개수가 요청 개수와 다릅니다.")
                from ultralytics.engine.results import Results
                from ultralytics.utils import ops

                for request, result, rgb in zip(batch, results, originals):
                    own = Profile("YOLO") if request.profile_enabled else None
                    with use(own), span("postprocess", stream):
                        boxes = result.boxes.data.clone()
                        boxes[:, :4] = ops.scale_boxes((_INPUT_SIZE, _INPUT_SIZE), boxes[:, :4], rgb.shape[-2:])
                        detection = Results(rgb.permute(1, 2, 0), path=result.path, names=result.names, boxes=boxes)
                        detection.orig_shape = tuple(rgb.shape[-2:])
                        detection.boxes.orig_shape = detection.orig_shape
                    request.profile = own
                    request.response = (
                        "ok",
                        detection,
                    )
                completion_event = torch.cuda.Event()
                completion_event.record(torch.cuda.current_stream(batch[0].image.device))
                for request in batch:
                    request.completion_event = completion_event
            except Exception as error:
                for request in batch:
                    request.response = ("error", f"{type(error).__name__}: {error}")
            finally:
                scope.__exit__(None, None, None)
                for request in batch:
                    if request.profile_enabled:
                        own = request.profile or Profile("YOLO")
                        own.merge(profile)
                        own.add("queue", dequeued_at - request.received_at)
                        request.profile = own
                    request.image = None
                    request.done.set()


def infer(model_path: Path, image: torch.Tensor, classes, confidence: float, gpu_id: int, *, ready_event=None, on_inference_complete=None, on_profile_complete=None):
    model_path = model_path.resolve()
    if not model_path.is_file():
        raise FileNotFoundError(model_path)
    with _workers_lock:
        worker = _workers.get(model_path)
        if worker is None:
            worker = _ModelWorker(model_path)
            _workers[model_path] = worker
    request = _InferenceRequest(image, classes, confidence, gpu_id, ready_event)
    request.profile_enabled = on_profile_complete is not None
    worker.requests.put(request)
    request.done.wait()
    if on_profile_complete is not None and request.profile is not None:
        on_profile_complete(request.profile)
    status, value = request.response
    if status == "error":
        raise RuntimeError(value)
    if request.completion_event is not None:
        request.completion_event.synchronize()
    if on_inference_complete is not None and request.inference_seconds is not None:
        on_inference_complete(request.inference_seconds)
    return value
