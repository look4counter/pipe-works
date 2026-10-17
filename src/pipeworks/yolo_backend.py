
import math
import re
from importlib import import_module
from pathlib import Path
from typing import Protocol

import torch
import yaml
from torch.utils._python_dispatch import TorchDispatchMode


class YoloBackend(Protocol):

    def infer(self, inputs): ...


def validate_backend(backend):
    if not isinstance(backend, str) or not (
        backend in ("torchscript", "ultralytics", "tensorrt")
        or re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*:[A-Za-z_]\w*", backend)
    ):
        raise ValueError(
            "backend는 torchscript, ultralytics, tensorrt 또는 모듈:클래스여야 합니다."
        )


def load_backend(model_path, gpu_id, backend):
    validate_backend(backend)
    if not torch.cuda.is_available():
        raise RuntimeError(
            "YOLO 추론에는 CUDA GPU가 필요하며 CPU 실행은 지원하지 않습니다."
        )
    if gpu_id >= torch.cuda.device_count():
        raise ValueError(f"사용할 수 없는 GPU 번호입니다: {gpu_id}")
    model_path = Path(model_path)
    if not model_path.is_file():
        raise FileNotFoundError(model_path)
    target = {
        "tensorrt": "pipeworks.yolo_backends.tensorrt:TensorRTBackend",
        "torchscript": "pipeworks.yolo_backends.torchscript:TorchScriptBackend",
        "ultralytics": "pipeworks.yolo_backends.ultralytics:UltralyticsBackend",
    }.get(backend, backend)
    module, name = target.split(":")
    instance = getattr(import_module(module), name)(model_path, gpu_id)
    if not callable(getattr(instance, "infer", None)):
        raise TypeError("모델 실행부는 infer(inputs)를 제공해야 합니다.")
    return instance


def _tensors(value):
    if isinstance(value, torch.Tensor):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from _tensors(child)
    elif isinstance(value, (tuple, list)):
        for child in value:
            yield from _tensors(child)


def validate_gpu(tensor, gpu_id):
    if not tensor.is_cuda or tensor.device.index != gpu_id:
        raise ValueError(
            "모델 텐서는 지정 GPU에 있어야 하며 CPU 또는 다른 GPU는 지원하지 않습니다."
        )


class GpuOnly(TorchDispatchMode):

    def __init__(self, gpu_id, scalar_constants=()):
        super().__init__()
        self.gpu_id = gpu_id
        self.scalar_constants = (
            scalar_constants
            if isinstance(scalar_constants, set)
            else set(scalar_constants)
        )
        self.error = None

    def __torch_dispatch__(self, func, types, args=(), kwargs=None):
        try:
            return self._dispatch(func, args, kwargs or {})
        except ValueError as error:
            self.error = error
            raise

    def _dispatch(self, func, args, kwargs):
        for tensor in _tensors((args, kwargs)):
            validate_gpu(tensor, self.gpu_id)
        device = kwargs.get("device")
        if device is not None:
            device = torch.device(device)
            index = (
                torch.cuda.current_device()
                if device.index is None and device.type == "cuda"
                else device.index
            )
            if device.type != "cuda" or index != self.gpu_id:
                raise ValueError(
                    "추론 중 CPU 또는 다른 GPU로 장치를 전환할 수 없습니다."
                )
        if (
            func == torch.ops.aten._local_scalar_dense.default
            and args[0].data_ptr() in self.scalar_constants
        ):
            # TorchScript는 불변 스칼라 그래프 상수를 메타데이터로 꺼낸다.
            return func(*args, **kwargs)
        if func in (
            torch.ops.aten._local_scalar_dense.default,
            torch.ops.aten.is_nonzero.default,
            torch.ops.aten.equal.default,
            torch.ops.aten.allclose.default,
        ):
            raise ValueError("추론 중 GPU 텐서 값을 CPU로 읽을 수 없습니다.")
        result = func(*args, **kwargs)
        for tensor in _tensors(result):
            validate_gpu(tensor, self.gpu_id)
        return result


def validate_inputs(inputs, gpu_id, *, batch=False):
    if isinstance(inputs, torch.Tensor):
        values = (inputs,)
    elif (
        isinstance(inputs, dict)
        and inputs
        and all(isinstance(name, str) and name.strip() for name in inputs)
    ):
        values = inputs.values()
    else:
        raise ValueError(
            "model_input은 GPU 텐서 또는 이름별 GPU 텐서 사전이어야 합니다."
        )
    for tensor in values:
        if not isinstance(tensor, torch.Tensor):
            raise ValueError("모든 모델 입력은 GPU 텐서여야 합니다.")  # noqa: TRY004 -- 입력 계약
        validate_gpu(tensor, gpu_id)
        if (
            tensor.layout != torch.strided
            or tensor.ndim < 1
            or any(size <= 0 for size in tensor.shape)
        ):
            raise ValueError("모델 입력은 각 축이 양수인 일반 GPU 텐서여야 합니다.")
        if batch and tensor.shape[0] != 1:
            raise ValueError("공유 배치 입력의 첫 축은 1이어야 합니다.")


def input_signature(inputs):
    if isinstance(inputs, torch.Tensor):
        return (None, inputs.dtype, tuple(inputs.shape[1:]))
    return tuple(
        (name, tensor.dtype, tuple(tensor.shape[1:]))
        for name, tensor in sorted(inputs.items())
    )


def contiguous_inputs(inputs):
    if isinstance(inputs, dict):
        return {name: tensor.contiguous() for name, tensor in inputs.items()}
    return inputs.contiguous()


def concatenate_inputs(inputs):
    first = inputs[0]
    if isinstance(first, dict):
        return {
            name: torch.cat([item[name] for item in inputs], dim=0) for name in first
        }
    return torch.cat(inputs, dim=0)


def normalize_outputs(output, gpu_id):
    outputs = {}

    def visit(value, path=""):
        if isinstance(value, torch.Tensor):
            validate_gpu(value, gpu_id)
            name = path or "output0"
            if name in outputs:
                raise ValueError(f"모델 출력 이름이 중복됩니다: {name}")
            outputs[name] = value.clone()
        elif isinstance(value, dict) and value:
            for name, child in value.items():
                if not isinstance(name, str) or not name.strip():
                    raise ValueError(
                        "모델 출력 이름은 비어 있지 않은 문자열이어야 합니다."
                    )
                visit(child, f"{path}/{name}" if path else name)
        elif isinstance(value, (list, tuple)) and value:
            for index, child in enumerate(value):
                name = f"output{index}"
                visit(child, f"{path}/{name}" if path else name)
        else:
            raise ValueError(
                "모델 출력은 GPU 텐서 또는 비어 있지 않은 중첩 텐서 컨테이너여야 합니다."
            )

    visit(output)
    return outputs


def validate_module_gpu(model, gpu_id):
    for tensor in (*model.parameters(), *model.buffers()):
        validate_gpu(tensor, gpu_id)


def batch_settings(model_path):
    config_path = Path(model_path).with_suffix(".yml")
    if not config_path.is_file():
        return 1, 0.0
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError(f"YOLO 배치 설정은 객체여야 합니다: {config_path}")  # noqa: TRY004 -- YAML 계약
    if any(key in config for key in ("timeout", "timeout_ms", "batch_timeout_ms")):
        raise ValueError("모델 YAML의 timeout·timeout_ms·batch_timeout_ms 대신 max_batch_wait_ms를 사용하세요.")
    size, timeout = config.get("max_batch_size"), config.get("max_batch_wait_ms")
    if isinstance(size, bool) or not isinstance(size, int) or size < 1:
        raise ValueError("max_batch_size는 1 이상의 정수여야 합니다.")
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not math.isfinite(timeout)
        or timeout < 0
    ):
        raise ValueError("max_batch_wait_ms는 0 이상의 유한한 밀리초여야 합니다.")
    return size, timeout / 1000
