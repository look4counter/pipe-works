
import torch

from pipeworks.yolo_backend import validate_module_gpu


class UltralyticsBackend:
    def __init__(self, model_path, gpu_id):
        from ultralytics.nn.tasks import load_checkpoint

        if model_path.suffix.lower() != ".pt":
            raise ValueError(
                "ultralytics 실행부는 PyTorch .pt 체크포인트만 지원합니다."
            )
        self.model, _ = load_checkpoint(
            str(model_path), device=torch.device("cuda", gpu_id), fuse=True
        )
        validate_module_gpu(self.model, gpu_id)
        self.dtype = torch.float32
        self.scalar_constants = set()
        self._stride_constants()

    def _stride_constants(self):
        # 스트라이드는 불변 모델 기하 메타데이터이며 이미지 데이터가 아니다.
        self.scalar_constants.clear()
        for module in self.model.modules():
            stride = getattr(module, "stride", None)
            if isinstance(stride, torch.Tensor) and stride.is_cuda:
                self.scalar_constants.update(
                    value.data_ptr() for value in stride.reshape(-1).unbind()
                )

    def infer(self, inputs):
        if isinstance(inputs, dict):
            if len(inputs) != 1:
                raise ValueError(
                    "ultralytics 체크포인트 실행부는 단일 이미지 입력만 지원합니다."
                )
            inputs = next(iter(inputs.values()))
        if (
            inputs.ndim != 4
            or inputs.shape[1] != 3
            or inputs.dtype not in (torch.float32, torch.float16)
        ):
            raise ValueError(
                "ultralytics 입력은 FP32/FP16 BCHW 3채널 이미지여야 합니다."
            )
        if self.dtype != inputs.dtype:
            self.model.to(dtype=inputs.dtype)
            self.dtype = inputs.dtype
            self._stride_constants()
        return self.model(inputs)
