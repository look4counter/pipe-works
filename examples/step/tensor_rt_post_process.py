import math
from types import SimpleNamespace

import torch
from ultralytics.engine.results import Boxes
from ultralytics.utils import YAML, ROOT
from ultralytics.utils.nms import non_max_suppression

from pipeworks.models import Step
from pipeworks.execution import current_model_stream
from pipeworks.detection_profile import span, use


class TensorRTPostProcess(Step):
    def __init__(self):
        self.names = YAML.load(ROOT / "cfg/datasets/coco.yaml")["names"]
        self.configure(SimpleNamespace())

    def configure(self, config):
        confidence = getattr(config, "confidence", .25)
        iou = getattr(config, "iou", .7)
        classes = getattr(config, "classes", None)
        max_det = getattr(config, "max_det", 300)
        output_name = getattr(config, "output_name", "output0")
        for name, value in (("confidence", confidence), ("iou", iou)):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{name}는 0 이상 1 이하의 유한한 숫자여야 합니다.")
        if classes is not None and (not isinstance(classes, list) or any(isinstance(n, bool) or not isinstance(n, int) or not 0 <= n < 80 for n in classes)):
            raise ValueError("classes는 0~79 정수 목록이어야 합니다.")
        if isinstance(max_det, bool) or not isinstance(max_det, int) or max_det < 1:
            raise ValueError("max_det는 양의 정수여야 합니다.")
        if not isinstance(output_name, str) or not output_name:
            raise ValueError("output_name은 비어 있지 않은 문자열이어야 합니다.")
        self.confidence, self.iou, self.classes, self.max_det, self.output_name = confidence, iou, classes, max_det, output_name

    def process(self, inputs):
        for item in inputs:
            profile = vars(item).pop("_tensor_rt_profile", None)
            state = "completed" if getattr(item, "model_output", None) is not None else "skipped"
            item.detections = None
            stream = current_model_stream() or getattr(item, "model_cuda_stream", item.cuda_stream)
            outputs = prediction = boxes = None
            try:
                outputs = getattr(item, "model_output", None)
                if outputs is not None:
                    prediction = outputs.get(self.output_name) if isinstance(outputs, dict) else None
                    if (not isinstance(prediction, torch.Tensor) or not prediction.is_cuda
                            or prediction.device != item.cuda_stream.device or prediction.dtype != torch.float32
                            or prediction.ndim != 3 or prediction.shape[0] != 1 or prediction.shape[1] != 84):
                        raise ValueError("YOLO11 출력은 같은 GPU의 FP32 (1, 84, N) 텐서여야 합니다.")
                    transform = item.tensor_rt_transform
                    with use(profile), span("postprocess", stream), torch.cuda.stream(stream), torch.no_grad():
                        # Consume the raw output in-place; only detections survive.
                        boxes = non_max_suppression(prediction, self.confidence, self.iou, classes=self.classes, max_det=self.max_det, nc=80)[0]
                        boxes[:, [0, 2]] = (boxes[:, [0, 2]] - transform.left) / transform.ratio
                        boxes[:, [1, 3]] = (boxes[:, [1, 3]] - transform.top) / transform.ratio
                        height, width = transform.shape
                        boxes[:, [0, 2]] = boxes[:, [0, 2]].clamp(0, width)
                        boxes[:, [1, 3]] = boxes[:, [1, 3]].clamp(0, height)
                        item.detections = SimpleNamespace(boxes=Boxes(boxes, transform.shape), names=self.names, orig_shape=transform.shape)
            except Exception:
                state = "error"
                raise
            finally:
                with use(profile), span("completion_wait"):
                    stream.synchronize()
                if profile is not None:
                    profile.finish(state)
                for name in ("model_input", "model_output", "tensor_rt_transform", "model_cuda_stream"):
                    vars(item).pop(name, None)
                outputs = prediction = boxes = None
            yield item
