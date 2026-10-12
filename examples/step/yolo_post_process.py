"""Filter GPU detection predictions and restore original image coordinates."""

import math
from types import SimpleNamespace

import torch
import torchvision  # noqa: F401 -- Ultralytics selects the compiled GPU NMS.
from ultralytics.engine.results import Boxes
from ultralytics.utils import ROOT, YAML
from ultralytics.utils.nms import non_max_suppression

from pipeworks.embedded.yolo_report import span, use
from pipeworks.inference_contract import clear_model_context, image_transform, pop_profile
from ultralytics.utils.ops import xywh2xyxy
from pipeworks.models import Step


def _names(value):
    if value is None:
        value = YAML.load(ROOT / "cfg/datasets/coco.yaml")["names"]
    if isinstance(value, (list, tuple)):
        value = dict(enumerate(value))
    if (
        not isinstance(value, dict)
        or not value
        or any(isinstance(key, bool) or not isinstance(key, int) for key in value)
        or set(value) != set(range(len(value)))
        or any(not isinstance(name, str) or not name.strip() for name in value.values())
    ):
        raise ValueError("names는 이름 목록 또는 0부터 연속하는 정수 키의 이름 사전이어야 합니다.")
    return dict(value)


class YoloPostProcess(Step):
    """Decode detection outputs independently of the inference backend."""

    def __init__(
        self,
        *,
        confidence=0.25,
        iou=0.7,
        classes=None,
        max_det=300,
        output_name="output0",
        names=None,
        end2end=False,
    ):
        self._set_config_defaults(
            confidence=confidence,
            iou=iou,
            classes=classes,
            max_det=max_det,
            output_name=output_name,
            names=names,
            end2end=end2end,
        )

    def configure(self, config):
        config = self._resolve_config(config)
        unknown = set(vars(config)) - set(self._config_defaults)
        if unknown:
            raise ValueError(f"알 수 없는 {type(self).__name__} 옵션: {sorted(unknown)}")
        names = _names(config.names)
        for name in ("confidence", "iou"):
            value = getattr(config, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or not 0 <= value <= 1
            ):
                raise ValueError(f"{name}는 0 이상 1 이하의 유한한 숫자여야 합니다.")
        if config.classes is not None and (
            not isinstance(config.classes, list)
            or any(
                isinstance(value, bool)
                or not isinstance(value, int)
                or value not in names
                for value in config.classes
            )
        ):
            raise ValueError("classes는 names에 존재하는 정수 ID 목록이어야 합니다.")
        if (
            isinstance(config.max_det, bool)
            or not isinstance(config.max_det, int)
            or config.max_det < 1
        ):
            raise ValueError("max_det는 양의 정수여야 합니다.")
        if not isinstance(config.output_name, str) or not config.output_name.strip():
            raise ValueError("output_name은 비어 있지 않은 문자열이어야 합니다.")
        if not isinstance(config.end2end, bool):
            raise ValueError("end2end는 불리언이어야 합니다.")
        self.__dict__.update(vars(config) | {"names": names})


    def _prediction(self, item):
        outputs = item.model_output
        prediction = outputs.get(self.output_name) if isinstance(outputs, dict) else None
        if (
            not isinstance(prediction, torch.Tensor)
            or not prediction.is_cuda
            or prediction.device != getattr(getattr(item, "cuda_stream", None), "device", None)
            or prediction.dtype not in (torch.float32, torch.float16)
            or prediction.ndim != 3
            or prediction.shape[0] != 1
            or (self.end2end and prediction.shape[2] != 6)
            or (not self.end2end and prediction.shape[1] != 4 + len(self.names))
        ):
            shape = "(1,N,6)" if self.end2end else f"(1,{4 + len(self.names)},N)"
            raise ValueError(f"YOLO 출력은 같은 GPU의 FP32/FP16 {shape} 텐서여야 합니다.")
        return prediction


    def _nms(self, prediction):
        prediction = prediction.float()
        if self.end2end:
            return non_max_suppression(
                prediction, self.confidence, self.iou, classes=self.classes,
                max_det=self.max_det, nc=len(self.names), end2end=True,
            )[0]
        scores, labels = prediction[0, 4:4 + len(self.names)].max(dim=0)
        keep = scores > self.confidence
        if self.classes is not None:
            allowed = labels.new_tensor(self.classes)
            keep &= (labels[:, None] == allowed).any(dim=1)
        rows = prediction[0].transpose(0, 1)
        rows[:, :4] = xywh2xyxy(rows[:, :4])
        # Select only the final six columns; consume raw coordinates in place.
        boxes = torch.cat(
            (rows[:, :4], scores[:, None], labels[:, None].float()), dim=1
        )[keep]
        if boxes.shape[0] == 0:
            return boxes
        if boxes.shape[0] > 30000:
            boxes = boxes[boxes[:, 4].argsort(descending=True)[:30000]]
        offset_boxes = boxes[:, :4] + boxes[:, 5:6] * 7680
        selected = torchvision.ops.nms(offset_boxes, boxes[:, 4], self.iou)[:self.max_det]
        return boxes[selected]


    def process(self, inputs):
        for item in inputs:
            profile = pop_profile(item)
            state = (
                "completed"
                if getattr(item, "model_output", None) is not None
                else "skipped"
            )
            stream = getattr(item, "cuda_stream", None)
            prediction = boxes = None
            try:
                detections = getattr(item, "detections", None)
                if detections is not None and not isinstance(detections, dict):
                    raise ValueError("YOLO detections는 모델 ID별 사전이어야 합니다.")
                model_id = getattr(item, "model_id", None)
                if not isinstance(model_id, str) or not model_id.strip():
                    raise ValueError("YOLO 후처리에는 비어 있지 않은 model_id가 필요합니다.")
                item.detections = dict(detections or {})
                item.detections[model_id] = None
                if getattr(item, "model_output", None) is not None:
                    prediction = self._prediction(item)
                    transform = image_transform(item)
                    if (
                        not callable(getattr(transform, "restore_boxes_", None))
                        or not hasattr(transform, "shape")
                    ):
                        raise ValueError("감지 후처리에는 image_transform이 필요합니다.")
                    with (
                        use(profile),
                        span("postprocess", stream),
                        torch.cuda.stream(stream),
                        torch.no_grad(),
                    ):
                        boxes = self._nms(prediction)
                        transform.restore_boxes_(boxes)
                        item.detections[model_id] = SimpleNamespace(
                            boxes=Boxes(boxes, transform.shape),
                            names=self.names,
                            orig_shape=transform.shape,
                        )
            except Exception:
                state = "error"
                raise
            finally:
                try:
                    if stream is not None:
                        with use(profile), span("completion_wait"):
                            stream.synchronize()
                except Exception:
                    state = "error"
                    raise
                finally:
                    if profile is not None:
                        profile.finish(state)
                    clear_model_context(item)
                    prediction = boxes = None
            yield item
