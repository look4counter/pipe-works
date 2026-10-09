from types import SimpleNamespace

import torch
import torch.nn.functional as F

from pipeworks.local_yolo import _nv12_to_rgb
from pipeworks.models import Step
from pipeworks.execution import current_model_stream, release_frame
from pipeworks.detection_profile import begin, span, use


class TensorRTPreProcess(Step):
    def process(self, inputs):
        streams = {}
        for item in inputs:
            profile = begin("TensorRT")
            if profile is not None:
                item._tensor_rt_profile = profile
            height = item.video_stream.codec_context.height
            width = item.video_stream.codec_context.width
            pixel_format = getattr(item.pixel_format, "name", item.pixel_format)
            if str(pixel_format).upper() != "NV12" or height <= 0 or width <= 0 or height % 2 or width % 2:
                if profile is not None:
                    profile.finish("error")
                raise ValueError("TensorRTPreProcess는 양의 짝수 크기 NV12 입력이 필요합니다.")
            producer = item.cuda_stream
            stream = current_model_stream() or streams.get(producer.device)
            if stream is None:
                stream = streams[producer.device] = torch.cuda.Stream(device=producer.device)
            ready = torch.cuda.Event()
            ready.record(producer)
            stream.wait_event(ready)
            item.model_cuda_stream = stream
            failed = False
            try:
                with use(profile), span("preprocess", stream), torch.cuda.stream(stream), torch.no_grad():
                    frame = torch.from_dlpack(item.frame)
                    if frame.device != item.cuda_stream.device or not frame.is_cuda or frame.dtype != torch.uint8:
                        raise ValueError("NV12 입력은 CUDA 스트림과 같은 GPU의 uint8 텐서여야 합니다.")
                    if frame.ndim == 1 and frame.numel() == height * width * 3 // 2:
                        frame = frame.reshape(height * 3 // 2, width)
                    if frame.ndim != 2 or frame.shape[0] < height * 3 // 2 or frame.shape[1] < width:
                        raise ValueError("NV12 입력 크기가 잘못되었습니다.")
                    rgb = _nv12_to_rgb(frame[:height * 3 // 2, :width])
                    frame_done = torch.cuda.Event()
                    frame_done.record(stream)
                    release_frame(ready_event=frame_done)
                    ratio = min(640 / height, 640 / width)
                    resized_h, resized_w = max(1, round(height * ratio)), max(1, round(width * ratio))
                    resized = F.interpolate(rgb.unsqueeze(0), size=(resized_h, resized_w), mode="bilinear", align_corners=False)
                    top, left = (640 - resized_h) // 2, (640 - resized_w) // 2
                    item.model_input = F.pad(resized, (left, 640 - resized_w - left, top, 640 - resized_h - top), value=114 / 255).contiguous()
                    item.tensor_rt_transform = SimpleNamespace(shape=(height, width), ratio=ratio, left=left, top=top)
                    item.detections = None
            except Exception:
                failed = True
                raise
            finally:
                with use(profile), span("completion_wait"):
                    stream.synchronize()
                if failed and profile is not None:
                    profile.finish("error")
            del frame, rgb, resized
            yield item
