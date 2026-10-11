"""Execute raw GPU tensors with TensorRT using engine-discovered I/O names."""

from contextvars import copy_context
import json
import logging
import math
from pathlib import Path
import time
from types import SimpleNamespace
from typing import Iterator

import torch
import yaml

from pipeworks.embedded.stream_report import record_inference
from pipeworks.models import PipelineContext, Step
from pipeworks.execution import current_model_stream
from pipeworks.detection_profile import _current, begin, span


logger = logging.getLogger(__name__)


def _load_model_config(model_path):
    path = model_path.with_suffix(".yml")
    if not path.is_file():
        return {}
    try:
        config = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise ValueError(f"TensorRT 모델 설정이 잘못되었습니다: {path}") from error
    if not isinstance(config, dict):
        raise ValueError("TensorRT 모델 설정은 객체여야 합니다.")
    if "timeout" in config:
        raise ValueError("모델 YAML의 timeout 대신 timeout_ms를 사용하세요.")
    if "profile_index" in config:
        raise ValueError("profile_index는 모델 YAML 대신 stream.yml의 TensorRTInference 아래에 설정하세요.")
    return config


def _engine_settings(model_path, config):
    plugins = config.get("plugins", [])
    if not isinstance(plugins, list) or any(not isinstance(plugin, str) or not plugin for plugin in plugins):
        raise ValueError("plugins는 공유 라이브러리 경로 문자열 목록이어야 합니다.")
    return tuple(model_path.parent / plugin for plugin in plugins)


def _validate_profile_index(profile_index):
    if isinstance(profile_index, bool) or not isinstance(profile_index, int) or profile_index < 0:
        raise ValueError("profile_index는 음수가 아닌 정수여야 합니다.")


def _torch_dtype(trt, dtype):
    for name, torch_name in (
        ("float32", "float32"), ("float16", "float16"), ("int8", "int8"),
        ("int32", "int32"), ("bool", "bool"), ("uint8", "uint8"),
        ("int64", "int64"), ("bfloat16", "bfloat16"), ("fp8", "float8_e4m3fn"),
    ):
        if hasattr(trt, name) and dtype == getattr(trt, name) and hasattr(torch, torch_name):
            return getattr(torch, torch_name)
    raise ValueError(f"지원하지 않는 TensorRT 자료형: {dtype}")


def _output_allocator(trt, dtype, device, shape):
    class Allocator(trt.IOutputAllocator):
        def __init__(self):
            trt.IOutputAllocator.__init__(self)
            self.element_size = torch.empty(0, dtype=dtype).element_size()
            self.reset(shape)

        def reset(self, shape):
            self.shape = shape
            self.raw = None
            self.buffer = None
            self.error = None
            if shape is not None:
                self._reserve(math.prod(shape) * self.element_size, 256)

        def _reserve(self, size, alignment):
            size, alignment = max(1, int(size)), max(1, int(alignment))
            if (self.buffer is None or self.buffer.numel() < size
                    or self.buffer.data_ptr() % alignment):
                self.raw = torch.empty(size + alignment, dtype=torch.uint8, device=device)
                offset = (-self.raw.data_ptr()) % alignment
                self.buffer = self.raw[offset:offset + size]
            return self.buffer.data_ptr()

        def reallocate_output(self, tensor_name, memory, size, alignment):
            try:
                return self._reserve(size, alignment)
            except Exception as error:
                self.error = error
                return 0

        def reallocate_output_async(self, tensor_name, memory, size, alignment, stream):
            return self.reallocate_output(tensor_name, memory, size, alignment)

        def notify_shape(self, tensor_name, shape):
            self.shape = tuple(shape)

        def output(self, strides):
            if self.error is not None:
                raise RuntimeError("TensorRT 출력 GPU 할당에 실패했습니다.") from self.error
            if self.shape is None or any(dimension < 0 for dimension in self.shape):
                raise RuntimeError("TensorRT 출력 형상이 결정되지 않았습니다.")
            if math.prod(self.shape) == 0:
                return torch.empty(self.shape, dtype=dtype, device=device)
            elements = 1 + sum((size - 1) * stride for size, stride in zip(self.shape, strides))
            size = elements * self.element_size
            if self.buffer is None or self.buffer.numel() < size:
                raise RuntimeError("TensorRT 출력 버퍼 크기가 출력 형상보다 작습니다.")
            return self.buffer[:size].view(dtype).as_strided(self.shape, strides)

    return Allocator()


class _EngineSession:
    def __init__(self, model_path: Path, plugins=(), profile_index=0):
        import tensorrt as trt

        self.context = self.engine = self.runtime = self.logger = None
        self.allocators = {}
        self.plugin_handles = []
        self.profile_index = profile_index
        self._profile_selected = False
        self.trt = trt
        self.logger = trt.Logger(trt.Logger.WARNING)
        if trt.init_libnvinfer_plugins(self.logger, "") is False:
            raise RuntimeError("TensorRT 표준 플러그인 초기화에 실패했습니다.")
        self.runtime = trt.Runtime(self.logger)
        self.runtime.engine_host_code_allowed = True
        self.plugin_handles = []
        for plugin in plugins:
            if not plugin.is_file():
                raise FileNotFoundError(plugin)
            handle = self.runtime.get_plugin_registry().load_library(str(plugin))
            if handle is None:
                raise RuntimeError(f"TensorRT 플러그인 라이브러리 로딩 실패: {plugin}")
            self.plugin_handles.append(handle)
        payload = model_path.read_bytes()
        if len(payload) >= 4:
            metadata_size = int.from_bytes(payload[:4], "little")
            if 0 < metadata_size <= min(1024 * 1024, len(payload) - 4):
                try:
                    metadata = json.loads(payload[4:4 + metadata_size])
                except (ValueError, UnicodeError):
                    pass
                else:
                    if isinstance(metadata, dict):
                        payload = payload[4 + metadata_size:]
        self.engine = self.runtime.deserialize_cuda_engine(payload)
        if self.engine is None:
            raise RuntimeError(f"TensorRT 엔진 역직렬화 실패: {model_path} (플러그인과 엔진 호환성을 확인하세요.)")
        if not 0 <= profile_index < self.engine.num_optimization_profiles:
            raise ValueError(f"profile_index {profile_index}가 엔진 프로파일 범위를 벗어났습니다. "
                             f"프로파일 수: {self.engine.num_optimization_profiles}")
        self.inputs, self.outputs, self.dtypes = [], [], {}
        self.input_shapes, self.profile_shapes = {}, {}
        for index in range(self.engine.num_io_tensors):
            name = self.engine.get_tensor_name(index)
            if self.engine.get_tensor_location(name) != trt.TensorLocation.DEVICE:
                raise ValueError(f"GPU에 없는 TensorRT 바인딩은 지원하지 않습니다: {name}")
            if self.engine.get_tensor_format(name, profile_index) != trt.TensorFormat.LINEAR:
                raise ValueError(f"LINEAR가 아닌 TensorRT 바인딩은 지원하지 않습니다: {name}")
            self.dtypes[name] = _torch_dtype(trt, self.engine.get_tensor_dtype(name))
            target = self.inputs if self.engine.get_tensor_mode(name) == trt.TensorIOMode.INPUT else self.outputs
            target.append(name)
            if target is self.inputs:
                shape = tuple(self.engine.get_tensor_shape(name))
                self.input_shapes[name] = shape
                if any(size < 0 for size in shape):
                    minimum, _, maximum = self.engine.get_tensor_profile_shape(name, profile_index)
                    self.profile_shapes[name] = (tuple(minimum), tuple(maximum))
        if not self.inputs or not self.outputs:
            raise ValueError("TensorRT 엔진에는 입력과 출력이 필요합니다.")
        self.context = self.engine.create_execution_context()
        if self.context is None:
            raise RuntimeError("TensorRT 실행 컨텍스트 생성에 실패했습니다.")
        self.allocators = {}

    def close(self):
        # 실행 컨텍스트와 엔진을 해제한 뒤 플러그인 레지스트리와 Runtime을 해제한다.
        self.context = None
        self.allocators = {}
        self.engine = None
        self.plugin_handles = []
        self.runtime = None
        self.logger = None

    def __del__(self):
        self.close()

    def infer(self, tensors, stream, report_context):
        with span("prepare"):
            if not self._profile_selected:
                if not self.context.set_optimization_profile_async(self.profile_index, stream.cuda_stream):
                    raise RuntimeError(f"TensorRT 프로파일 {self.profile_index} 선택에 실패했습니다.")
                self._profile_selected = True
            self._bind(tensors, stream)
        started_at = time.perf_counter()
        try:
            with span("inference", stream):
                if not self.context.execute_async_v3(stream_handle=stream.cuda_stream):
                    raise RuntimeError("TensorRT 추론 실행에 실패했습니다.")
        finally:
            with span("completion_wait"):
                stream.synchronize()
            report_context.run(record_inference, time.perf_counter() - started_at)
        return {name: allocator.output(tuple(self.context.get_tensor_strides(name)))
                for name, allocator in self.allocators.items()}

    def _bind(self, tensors, stream):
        if isinstance(tensors, torch.Tensor):
            if len(self.inputs) != 1:
                raise ValueError("다중 입력 엔진에는 입력 이름별 GPU 텐서 사전이 필요합니다.")
            tensors = {self.inputs[0]: tensors}
        if set(tensors) != set(self.inputs):
            raise ValueError(f"TensorRT 입력 이름이 일치하지 않습니다. 필요: {self.inputs}, 제공: {list(tensors)}")
        for name, tensor in tensors.items():
            if tensor.dtype != self.dtypes[name]:
                raise ValueError(f"TensorRT 입력 자료형 불일치: {name}, 필요: {self.dtypes[name]}, 제공: {tensor.dtype}")
            if tensor.device != stream.device or not tensor.is_contiguous():
                raise ValueError(f"TensorRT 입력은 실행 GPU의 연속 텐서여야 합니다: {name}")
            expected = self.input_shapes[name]
            if (len(expected) != tensor.ndim
                    or any(size >= 0 and size != actual for size, actual in zip(expected, tensor.shape))):
                raise ValueError(f"TensorRT 입력 형상 불일치: {name}")
            bounds = self.profile_shapes.get(name)
            if bounds is not None:
                minimum, maximum = bounds
                if any(actual < low or actual > high
                       for actual, low, high in zip(tensor.shape, minimum, maximum)):
                    raise ValueError(f"TensorRT 입력 형상이 프로파일 {self.profile_index} 범위를 벗어났습니다: {name}")
            if not self.context.set_input_shape(name, tuple(tensor.shape)):
                raise ValueError(f"TensorRT 입력 형상이 프로파일 {self.profile_index} 범위를 벗어났습니다: {name}")
            if not self.context.set_tensor_address(name, tensor.data_ptr()):
                raise RuntimeError(f"TensorRT 입력 주소 설정 실패: {name}")
        missing = self.context.infer_shapes()
        if missing:
            raise ValueError(f"TensorRT 형상 추론에 필요한 입력이 누락되었습니다: {missing}")
        for name, tensor in tensors.items():
            strides = tuple(self.context.get_tensor_strides(name))
            if (len(strides) != tensor.ndim
                    or any(size > 1 and expected != actual
                           for size, expected, actual in zip(tensor.shape, strides, tensor.stride()))):
                raise ValueError(f"TensorRT 입력 메모리 배치가 연속 GPU 텐서와 일치하지 않습니다: {name}")
        for name in self.outputs:
            shape = tuple(self.context.get_tensor_shape(name))
            known_shape = shape if all(size >= 0 for size in shape) else None
            allocator = self.allocators.get(name)
            if allocator is None:
                allocator = _output_allocator(self.trt, self.dtypes[name], stream.device, known_shape)
                if not self.context.set_output_allocator(name, allocator):
                    raise RuntimeError(f"TensorRT 출력 할당기 설정 실패: {name}")
                self.allocators[name] = allocator
            else:
                # TensorRT retains registered Python allocators until context teardown.
                # Reuse the callback owner, but preserve earlier output Tensor storage.
                allocator.reset(known_shape)
            address = allocator.buffer.data_ptr() if allocator.buffer is not None else 0
            if not self.context.set_tensor_address(name, address):
                raise RuntimeError(f"TensorRT 출력 주소 설정 실패: {name}")


class TensorRTInference(Step):
    def __init__(self, model_path: Path, *, batch: bool = False, gpu_id: int = 0,
                 inference_interval_frame: int = 1, profile_index: int = 0,
                 id: str | None = None):
        if not isinstance(batch, bool):
            raise ValueError("batch는 불리언이어야 합니다.")
        self.batch = batch
        self.model_path = Path(model_path)
        self._set_config_defaults(gpu_id=gpu_id, inference_interval_frame=inference_interval_frame,
                                  profile_index=profile_index, id=id)

    def configure(self, config: SimpleNamespace):
        config = self._resolve_config(config)
        if hasattr(config, "inference_interval"):
            raise ValueError("inference_interval 대신 프레임 단위의 inference_interval_frame을 사용하세요.")
        gpu_id = getattr(config, "gpu_id", 0)
        interval = getattr(config, "inference_interval_frame", 1)
        profile_index = getattr(config, "profile_index", 0)
        model_id = self.model_path.name if config.id is None else config.id
        if not isinstance(model_id, str) or not model_id.strip():
            raise ValueError("id는 비어 있지 않은 문자열 또는 null이어야 합니다.")
        _validate_profile_index(profile_index)
        if isinstance(gpu_id, bool) or not isinstance(gpu_id, int) or gpu_id < 0:
            raise ValueError("gpu_id는 음수가 아닌 정수여야 합니다.")
        if isinstance(interval, bool) or not isinstance(interval, int) or interval < 1:
            raise ValueError("inference_interval_frame은 1 이상의 정수여야 합니다.")
        self.gpu_id, self.inference_interval_frame = gpu_id, interval
        self.profile_index = profile_index
        self.id = model_id

    def _model_settings(self):
        return _engine_settings(self.model_path, _load_model_config(self.model_path))

    def _prepare_inputs(self, item):
        inputs = getattr(item, "model_input", None)
        if isinstance(inputs, torch.Tensor):
            tensors = {None: inputs}
        elif isinstance(inputs, dict) and inputs and all(isinstance(name, str) for name in inputs):
            tensors = inputs
        else:
            raise ValueError("model_input must be a GPU tensor or a named tensor mapping.")
        for tensor in tensors.values():
            if not isinstance(tensor, torch.Tensor) or not tensor.is_cuda or tensor.device.index != self.gpu_id:
                raise ValueError("model_input GPU must match gpu_id.")
        producer = current_model_stream() or getattr(item, "model_cuda_stream", None)
        if producer is None:
            producer = getattr(item, "cuda_stream", None)
        if producer is None:
            producer = torch.cuda.current_stream(self.gpu_id)
        if producer.device.index != self.gpu_id:
            raise ValueError("Input CUDA stream GPU must match gpu_id.")
        ready = torch.cuda.Event()
        ready.record(producer)
        return inputs, ready

    def process(self, inputs: Iterator[PipelineContext]) -> Iterator[PipelineContext]:
        # 원래 생성기를 유지하여 엔진/스트림 수명을 바꾸지 않는다.
        current = [None, None, False]

        def profiled_inputs():
            for item in inputs:
                item.model_id = self.id
                inherited = getattr(item, "_tensor_rt_profile", None)
                profile = inherited or begin("TensorRT")
                current[:] = item, profile, inherited is None
                _current.set(profile)
                yield item

        outputs = self._process(profiled_inputs())
        try:
            while True:
                token = _current.set(None)
                try:
                    item = next(outputs)
                except StopIteration:
                    break
                finally:
                    _current.reset(token)
                profile = current[1]
                if profile is not None and current[2]:
                    profile.finish("completed" if item.model_output is not None else "skipped")
                yield item
        except Exception:
            if current[1] is not None:
                current[1].finish("error")
            raise
        finally:
            outputs.close()

    def _process(self, inputs: Iterator[PipelineContext]) -> Iterator[PipelineContext]:
        if self.batch:
            from pipeworks.local_tensor_rt import infer

            for index, item in enumerate(inputs):
                item.model_output = None
                if index % self.inference_interval_frame == 0:
                    tensors, ready_event = self._prepare_inputs(item)
                    profile = _current.get()
                    options = {"on_profile_complete": profile.merge} if profile is not None else {}
                    item.model_output = infer(
                        self.model_path, tensors, self.gpu_id,
                        profile_index=self.profile_index,
                        ready_event=ready_event, on_inference_complete=record_inference, **options,
                    )
                yield item
            return
        plugins = self._model_settings()
        session = stream = None
        session_settings = None
        try:
            for index, item in enumerate(inputs):
                item.model_output = None
                if index % self.inference_interval_frame == 0:
                    tensors, ready_event = self._prepare_inputs(item)
                    settings = self.gpu_id, self.profile_index
                    if session_settings != settings:
                        if stream is not None:
                            stream.synchronize()
                        if session is not None:
                            session.close()
                        session = None
                        session_settings = settings
                        stream = current_model_stream() or torch.cuda.Stream(device=self.gpu_id)
                    with torch.cuda.stream(stream):
                        try:
                            # Keep input ordering on the GPU, including caller-owned streams.
                            with span("input_wait"):
                                stream.wait_event(ready_event)
                            tensors = ({name: tensor.contiguous() for name, tensor in tensors.items()}
                                       if isinstance(tensors, dict) else tensors.contiguous())
                            if session is None:
                                with span("prepare"):
                                    session = _EngineSession(self.model_path, plugins, self.profile_index)
                            item.model_output = session.infer(tensors, stream, copy_context())
                        finally:
                            with span("completion_wait"):
                                stream.synchronize()
                yield item
        finally:
            if stream is not None:
                stream.synchronize()
            if session is not None:
                session.close()
