
import time
from contextlib import nullcontext
from contextvars import copy_context
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import torch

from pipeworks.embedded.stream_report import record_inference
from pipeworks.embedded.yolo_report import begin, span, use, backend_kind, _current
from pipeworks.inference_contract import bind_profile, inherited_profile
from pipeworks.backend import Backend
from pipeworks.models import PipelineContext, Step
from pipeworks.yolo_backends.tensorrt import (
    _EngineSession, TensorRTBackend, _load_model_config, _validate_profile_index,
)
from pipeworks.yolo_backend import (
    GpuOnly,
    contiguous_inputs,
    load_backend,
    normalize_outputs,
    validate_backend,
    validate_inputs,
)

_validate_input = validate_inputs


class _Session:
    def __init__(self, path, gpu_id, backend="torchscript"):
        self.gpu_id = gpu_id
        self.backend = load_backend(path, gpu_id, backend)

    def infer(self, inputs, stream):
        constants = getattr(self.backend, "scalar_constants", ())
        if not isinstance(constants, (set, tuple, list)):
            constants = ()
        guard = (
            nullcontext()
            if isinstance(self.backend, TensorRTBackend)
            else GpuOnly(self.gpu_id, constants)
        )
        try:
            with torch.no_grad(), guard:
                with span("inference", stream):
                    output = self.backend.infer(inputs)
                with span("output_copy", stream):
                    return normalize_outputs(output, self.gpu_id)
        except Exception as error:
            # TorchScript는 Python 디스패치 예외 메시지를 제거할 수 있다.
            if getattr(guard, "error", None) is not None and guard.error is not error:
                raise guard.error from error
            raise


class YoloInference(Step):
    def __init__(
        self,
        model_path: Path,
        *,
        batch: bool = False,
        gpu_id: int = 0,
        id: str | None = None,
        backend: Backend | str,
        profile_index: int = 0,
    ) -> None:
        if not isinstance(batch, bool):
            raise ValueError("batch는 불리언이어야 합니다.")  # noqa: TRY004 -- 설정 오류 계약을 보존한다
        self.model_path = Path(model_path)
        self.batch = batch
        self._set_config_defaults(
            gpu_id=gpu_id,
            id=id,
            backend=backend,
            profile_index=profile_index,
        )

    def configure(self, config: SimpleNamespace) -> None:
        if hasattr(config, "inference_interval_frame"):
            raise ValueError("inference_interval_frame은 삭제되었습니다. EveryNFrames의 interval_frames를 사용하세요.")
        config = self._resolve_config(config)
        model_id = self.model_path.name if config.id is None else config.id
        if not isinstance(model_id, str) or not model_id.strip():
            raise ValueError("id는 비어 있지 않은 문자열 또는 null이어야 합니다.")
        if (
            isinstance(config.gpu_id, bool)
            or not isinstance(config.gpu_id, int)
            or config.gpu_id < 0
        ):
            raise ValueError("gpu_id는 음수가 아닌 정수여야 합니다.")
        validate_backend(config.backend)
        _validate_profile_index(config.profile_index)
        if config.backend != Backend.TENSORRT and config.profile_index != 0:
            raise ValueError("profile_index는 TensorRT 실행부에서만 지정할 수 있습니다.")
        self.profile_index = config.profile_index
        self.backend = (
            Backend(config.backend)
            if config.backend in tuple(Backend)
            else config.backend
        )
        self.gpu_id = config.gpu_id
        self.id = model_id

    @property
    def report_kind(self):
        return backend_kind(self.backend)

    def _prepare_inputs(self, item):
        tensor = getattr(item, "model_input", None)
        _validate_input(
            tensor, self.gpu_id,
            batch=self.batch and self.backend != Backend.TENSORRT,
        )
        stream = getattr(item, "cuda_stream", None)
        if stream is None:
            stream = torch.cuda.current_stream(self.gpu_id)
            item.cuda_stream = stream
        if stream.device.index != self.gpu_id:
            raise ValueError("입력 CUDA 스트림의 GPU는 gpu_id와 일치해야 합니다.")
        ready = torch.cuda.Event()
        ready.record(stream)
        return tensor, ready

    def process(self, inputs: Iterator[PipelineContext]) -> Iterator[PipelineContext]:
        if self.backend == Backend.TENSORRT:
            yield from self._process_tensor_rt_profiled(inputs)
        else:
            yield from self._process_yolo(inputs)

    def _process_yolo(self, inputs: Iterator[PipelineContext]) -> Iterator[PipelineContext]:
        session = settings = stream = None
        try:
            for item in inputs:
                item.model_id = self.id
                item.model_output = None
                inherited = bind_profile(inherited_profile(item), self.report_kind)
                profile = inherited or begin(self.report_kind)
                try:
                    tensor, ready = self._prepare_inputs(item)
                    with use(profile):
                        if self.batch:
                            from pipeworks.local_yolo_inference import infer

                            options = (
                                {"on_profile_complete": profile.merge}
                                if profile is not None
                                else {}
                            )
                            item.model_output = infer(
                                self.model_path,
                                tensor,
                                self.gpu_id,
                                backend=self.backend,
                                ready_event=ready,
                                on_inference_complete=record_inference,
                                **options,
                            )
                        else:
                            stream = item.cuda_stream
                            with torch.cuda.stream(stream):
                                try:
                                    with span("input_wait"):
                                        stream.wait_event(ready)
                                    with span("input_copy", stream):
                                        tensor = contiguous_inputs(tensor)
                                    key = self.gpu_id, self.backend
                                    if settings != key:
                                        session = None
                                        with span("prepare"):
                                            session = _Session(self.model_path, *key)
                                        settings = key
                                    started = time.perf_counter()
                                    output = session.infer(tensor, stream)
                                finally:
                                    with span("completion_wait"):
                                        stream.synchronize()
                                record_inference(time.perf_counter() - started)
                                item.model_output = output
                except Exception:
                    if profile is not None:
                        profile.finish("error")
                    raise
                else:
                    if profile is not None and inherited is None:
                        profile.finish()
                yield item
        finally:
            if stream is not None:
                stream.synchronize()

    def _process_tensor_rt_profiled(self, inputs: Iterator[PipelineContext]) -> Iterator[PipelineContext]:
        # 원래 생성기를 유지하여 엔진/스트림 수명을 바꾸지 않는다.
        current = [None, None, False]

        def profiled_inputs():
            for item in inputs:
                item.model_id = self.id
                inherited = bind_profile(inherited_profile(item), "TensorRT")
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
                    profile.finish(
                        "completed" if item.model_output is not None else "skipped"
                    )
                yield item
        except Exception:
            if current[1] is not None:
                current[1].finish("error")
            raise
        finally:
            outputs.close()

    def _process(self, inputs: Iterator[PipelineContext]) -> Iterator[PipelineContext]:
        if self.batch:
            from pipeworks.local_yolo_inference import infer

            for item in inputs:
                item.model_output = None
                tensors, ready_event = self._prepare_inputs(item)
                profile = _current.get()
                options = (
                    {"on_profile_complete": profile.merge}
                    if profile is not None
                    else {}
                )
                item.model_output = infer(
                    self.model_path,
                    tensors,
                    self.gpu_id,
                    backend=self.backend,
                    profile_index=self.profile_index,
                    ready_event=ready_event,
                    on_inference_complete=record_inference,
                    **options,
                )
                yield item
            return
        _load_model_config(self.model_path)
        session = stream = None
        session_settings = None
        try:
            for item in inputs:
                item.model_output = None
                tensors, ready_event = self._prepare_inputs(item)
                settings = self.gpu_id, self.profile_index
                if session_settings != settings:
                    if stream is not None:
                        stream.synchronize()
                    if session is not None:
                        session.close()
                    session = None
                    session_settings = settings
                stream = item.cuda_stream
                with torch.cuda.stream(stream):
                    try:
                        # 호출자 소유 스트림을 포함해 GPU에서 입력 처리 순서를 유지한다.
                        with span("input_wait"):
                            stream.wait_event(ready_event)
                        tensors = (
                            {
                                name: tensor.contiguous()
                                for name, tensor in tensors.items()
                            }
                            if isinstance(tensors, dict)
                            else tensors.contiguous()
                        )
                        if session is None:
                            with span("prepare"):
                                session = _EngineSession(
                                    self.model_path, self.profile_index
                                )
                        item.model_output = session.infer(
                            tensors, stream, copy_context()
                        )
                    finally:
                        with span("completion_wait"):
                            stream.synchronize()
                yield item
        finally:
            if stream is not None:
                stream.synchronize()
            if session is not None:
                session.close()
