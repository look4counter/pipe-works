import math

import torch
from torch import nn
from torch.nn import functional as F
from torchvision.models import resnet18

from pipeworks.yolo_backend import validate_gpu, validate_module_gpu


class _PatchCore(nn.Module):
    """학습 프로젝트의 patchcore-v1 추론 연산을 보존한다."""

    def __init__(self, imgsz):
        super().__init__()
        self.imgsz = imgsz
        self.backbone = resnet18(weights=None)
        self.backbone.requires_grad_(False)
        self.register_buffer("memory_bank", torch.empty(0, 384))
        self.register_buffer(
            "mean", torch.tensor([0.485, 0.456, 0.406]).view(1, 3, 1, 1)
        )
        self.register_buffer(
            "std", torch.tensor([0.229, 0.224, 0.225]).view(1, 3, 1, 1)
        )
        self.eval()

    def embedding(self, images):
        x = F.interpolate(
            images, (self.imgsz, self.imgsz), mode="bilinear", align_corners=False
        )
        x = (x - self.mean) / self.std
        net = self.backbone
        x = net.maxpool(net.relu(net.bn1(net.conv1(x))))
        first = net.layer2(net.layer1(x))
        second = net.layer3(first)
        first = F.avg_pool2d(first, 3, 1, 1)
        second = F.avg_pool2d(second, 3, 1, 1)
        second = F.interpolate(
            second, first.shape[-2:], mode="bilinear", align_corners=False
        )
        return torch.cat((first, second), dim=1)

    def forward(self, images):
        embeddings = self.embedding(images)
        batch, channels, height, width = embeddings.shape
        patches = embeddings.permute(0, 2, 3, 1).reshape(-1, channels)
        distances = []
        for chunk in patches.split(256):
            nearest = torch.full((len(chunk),), float("inf"), device=chunk.device)
            for memory in self.memory_bank.split(1024):
                squared = (
                    chunk.square().sum(1, keepdim=True)
                    + memory.square().sum(1)[None]
                    - 2 * chunk @ memory.T
                )
                nearest = torch.minimum(nearest, squared.clamp_min_(0).amin(1))
            distances.append(nearest.sqrt())
        maps = torch.cat(distances).reshape(batch, 1, height, width)
        scores = maps.flatten(1).amax(1)
        maps = F.interpolate(
            maps, images.shape[-2:], mode="bilinear", align_corners=False
        )
        return {"pred_score": scores, "anomaly_map": maps[:, 0]}


class PatchCoreBackend:
    """ResNet18 기반 patchcore-v1 체크포인트의 CUDA 실행부."""

    def __init__(self, model_path, gpu_id):
        payload = torch.load(model_path, map_location="cpu", weights_only=True)
        if (
            not isinstance(payload, dict)
            or payload.get("format") != "patchcore-v1"
            or payload.get("backbone") != "resnet18"
        ):
            raise ValueError("ResNet18 기반 patchcore-v1 체크포인트가 필요합니다.")
        imgsz = payload.get("imgsz")
        if isinstance(imgsz, bool) or not isinstance(imgsz, int) or imgsz < 1:
            raise ValueError("PatchCore imgsz는 양의 정수여야 합니다.")
        state = payload.get("state_dict")
        if not isinstance(state, dict) or not state:
            raise ValueError("PatchCore 가중치 사전이 필요합니다.")
        memory = state.get("memory_bank")
        if (
            not isinstance(memory, torch.Tensor)
            or memory.ndim != 2
            or memory.shape[0] < 1
            or memory.shape[1] != 384
            or memory.dtype != torch.float32
        ):
            raise ValueError(
                "PatchCore 메모리 뱅크는 비어 있지 않은 float32 [N,384]여야 합니다."
            )
        for value in state.values():
            if not isinstance(value, torch.Tensor) or value.layout != torch.strided:
                raise ValueError("PatchCore 가중치는 일반 텐서여야 합니다.")
            if value.is_floating_point() and (
                value.dtype != torch.float32 or not torch.isfinite(value).all()
            ):
                raise ValueError("PatchCore 가중치는 유한한 float32여야 합니다.")
        if "std" not in state or not (state["std"] > 0).all():
            raise ValueError("PatchCore 정규화 표준편차는 양수여야 합니다.")
        self.threshold = payload.get("threshold")
        if self.threshold is not None and (
            isinstance(self.threshold, bool)
            or not isinstance(self.threshold, (float, int))
            or not math.isfinite(self.threshold)
        ):
            raise ValueError("PatchCore 임계값은 유한한 숫자 또는 null이어야 합니다.")
        self.metadata = payload.get("metadata", {})
        if not isinstance(self.metadata, dict):
            raise ValueError("PatchCore 메타데이터는 사전이어야 합니다.")  # noqa: TRY004 -- 체크포인트 오류 계약
        self.model = _PatchCore(imgsz)
        self.model.memory_bank = torch.empty_like(memory)
        try:
            self.model.load_state_dict(state, strict=True)
        except RuntimeError as error:
            raise ValueError(
                "PatchCore 가중치가 ResNet18 모델 구조와 일치하지 않습니다."
            ) from error
        self.gpu_id = gpu_id
        self.model.to(torch.device("cuda", gpu_id)).eval()
        validate_module_gpu(self.model, gpu_id)

    @torch.no_grad()
    def infer(self, inputs):
        if (
            not isinstance(inputs, torch.Tensor)
            or inputs.ndim != 4
            or inputs.shape[1] != 3
            or any(size <= 0 for size in inputs.shape)
            or inputs.dtype != torch.float32
            or inputs.layout != torch.strided
        ):
            raise ValueError(
                "PatchCore 입력은 RGB float32 [B,3,H,W] GPU 텐서여야 합니다."
            )
        validate_gpu(inputs, self.gpu_id)
        return self.model(inputs)
