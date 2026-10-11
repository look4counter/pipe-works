import math
from types import SimpleNamespace

import torch
# Ultralytics가 컴파일된 NMS를 선택하도록 모듈 초기화 시 로드한다.
import torchvision  # noqa: F401
from ultralytics.engine.results import Boxes
from ultralytics.utils import YAML, ROOT
from ultralytics.utils.ops import xywh2xyxy
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

    def _nms(self, prediction):
        # Preserve the library's six-column special case.
        if prediction.shape[-1] == 6:
            return non_max_suppression(prediction, self.confidence, self.iou,
                classes=self.classes, max_det=self.max_det, nc=80)[0]
        scores, labels = prediction[0, 4:84].max(dim=0)
        keep = scores > self.confidence
        if self.classes is not None:
            allowed = labels.new_tensor(self.classes)
            keep &= (labels[:, None] == allowed).any(dim=1)
        rows = prediction[0].transpose(0, 1)
        rows[:, :4] = xywh2xyxy(rows[:, :4])
        # One dynamic selection of six columns replaces repeated 84-column
        # candidate selection, score filtering, and class filtering.
        boxes = torch.cat((rows[:, :4], scores[:, None], labels[:, None].float()), dim=1)[keep]
        if boxes.shape[0] == 0:
            return boxes
        if boxes.shape[0] > 30000:
            boxes = boxes[boxes[:, 4].argsort(descending=True)[:30000]]
        offset_boxes = boxes[:, :4] + boxes[:, 5:6] * 7680
        selected = torchvision.ops.nms(offset_boxes, boxes[:, 4], self.iou)[:self.max_det]
        return boxes[selected]

    def process(self, inputs):
        for item in inputs:
            profile = vars(item).pop("_tensor_rt_profile", None)
            state = "completed" if getattr(item, "model_output", None) is not None else "skipped"
            stream = current_model_stream() or getattr(item, "model_cuda_stream", item.cuda_stream)
            outputs = prediction = boxes = None
            try:
                detections = getattr(item, "detections", None)
                if detections is not None and not isinstance(detections, dict):
                    raise ValueError("TensorRT detections는 모델 ID별 사전이어야 합니다.")
                # Async contexts can share the mapping; replace it without mutating it.
                item.detections = dict(detections or {})
                model_id = getattr(item, "model_id", None)
                if model_id is not None:
                    if not isinstance(model_id, str) or not model_id.strip():
                        raise ValueError("model_id는 비어 있지 않은 문자열이어야 합니다.")
                    item.detections[model_id] = None
                outputs = getattr(item, "model_output", None)
                if outputs is not None:
                    if model_id is None:
                        raise ValueError("TensorRT 후처리에는 추론 단계의 model_id가 필요합니다.")
                    prediction = outputs.get(self.output_name) if isinstance(outputs, dict) else None
                    if (not isinstance(prediction, torch.Tensor) or not prediction.is_cuda
                            or prediction.device != item.cuda_stream.device or prediction.dtype != torch.float32
                            or prediction.ndim != 3 or prediction.shape[0] != 1 or prediction.shape[1] != 84):
                        raise ValueError("YOLO11 출력은 같은 GPU의 FP32 (1, 84, N) 텐서여야 합니다.")
                    transform = item.tensor_rt_transform
                    with use(profile), span("postprocess", stream), torch.cuda.stream(stream), torch.no_grad():
                        # Consume the raw output in-place; only detections survive.
                        boxes = self._nms(prediction)
                        transform.restore_boxes_(boxes)
                        item.detections[model_id] = SimpleNamespace(boxes=Boxes(boxes, transform.shape), names=self.names, orig_shape=transform.shape)
            except Exception:
                state = "error"
                raise
            finally:
                with use(profile), span("completion_wait"):
                    stream.synchronize()
                if profile is not None:
                    profile.finish(state)
                for name in ("model_input", "model_output", "tensor_rt_transform", "model_cuda_stream", "model_id"):
                    vars(item).pop(name, None)
                outputs = prediction = boxes = None
            yield item
