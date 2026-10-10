"""Run Steps without input copies; drop timed-out frames still in use."""

from contextlib import nullcontext
from contextvars import Context, copy_context
from dataclasses import dataclass, field
import logging
import math
from threading import Condition, Event, Lock, Thread
import time
from types import SimpleNamespace
from typing import Iterator

import torch

from pipeworks.models import PipelineContext, Step
from pipeworks.execution import _input_scope, _frame_scope, _model_stream_scope
from pipeworks.hotswap import Hotswap, is_embedded_step
from pipeworks.detection_profile import status


logger = logging.getLogger(__name__)
_SHARED_FIELDS = ("cuda_stream", "video_stream", "audio_stream")


@dataclass
class _Request:
    owner: PipelineContext | None
    deadline: float
    context: Context = field(default_factory=copy_context)
    item: PipelineContext | None = None
    ready_events: list = field(default_factory=list)
    input_tensors: list = field(default_factory=list)
    done: Event = field(default_factory=Event)
    expired: Event = field(default_factory=Event)
    consumed: bool = False
    result: PipelineContext | None = None
    completed_at: float | None = None
    error: Exception | None = None
    prepared: Event = field(default_factory=Event)
    release_requested: bool = False
    release_event: object | None = None
    frame_release_requested: bool = False
    frame_release_event: object | None = None
    input_drained: bool = False


def _tensors(value, found, seen):
    """Collect tensor leaves without traversing opaque shared stream resources."""
    if id(value) in seen:
        return
    seen.add(id(value))
    if isinstance(value, torch.Tensor):
        found[id(value)] = value
    elif isinstance(value, dict):
        for key, item in value.items():
            _tensors(key, found, seen)
            _tensors(item, found, seen)
    elif isinstance(value, (list, tuple, set, frozenset)):
        for item in value:
            _tensors(item, found, seen)
    elif hasattr(value, "__dict__") and not isinstance(value, type):
        _tensors(vars(value), found, seen)


def _prepare(request):
    """Retain input storage and separate attributes without copying data."""
    source = request.owner
    stream = getattr(source, "cuda_stream", None)
    fields = vars(source).copy()
    frame = fields.get("frame")
    if frame is not None and not isinstance(frame, torch.Tensor) and hasattr(frame, "__dlpack__"):
        with torch.cuda.stream(stream) if stream is not None else nullcontext():
            fields["frame"] = torch.from_dlpack(frame)
    request.owner = PipelineContext(**fields)
    request.item = PipelineContext(**fields)
    tensors = {}
    shared = {id(fields[name]) for name in _SHARED_FIELDS if name in fields}
    _tensors(fields, tensors, shared)
    request.input_tensors = list(tensors.values())
    streams = {}
    if stream is not None:
        streams[stream.device] = stream
    for tensor in request.input_tensors:
        if tensor.is_cuda and tensor.device not in streams:
            streams[tensor.device] = torch.cuda.current_stream(tensor.device)
    for producer in streams.values():
        event = torch.cuda.Event()
        event.record(producer)
        request.ready_events.append(event)


class _InputSlot(Iterator[PipelineContext]):
    def __init__(self):
        self.condition = Condition()
        self.request: _Request | None = None
        self.closed = False

    def offer(self, request):
        with self.condition:
            if self.closed or self.request is not None:
                return False
            self.request = request
            return True

    def publish(self):
        with self.condition:
            self.condition.notify_all()

    def wait(self):
        with self.condition:
            while self.request is None and not self.closed:
                self.condition.wait()
            return self.request

    def __next__(self):
        with self.condition:
            request = self.request
            if request is None:
                if self.closed:
                    raise StopIteration
                raise RuntimeError("CudaAsync 단계는 출력 전에 추가 입력을 요구할 수 없습니다.")
            if request.consumed:
                raise RuntimeError("CudaAsync 단계는 입력마다 정확히 한 번 출력해야 합니다.")
            request.consumed = True
            return request.item

    def finish(self, request, result):
        with self.condition:
            request.completed_at = time.monotonic()
            borrowed_frame = any(getattr(item, "_decode_buffer", None) is not None
                                 for item in (request.owner, request.item, result) if item is not None)
            if not self.closed and not request.expired.is_set() and request.completed_at <= request.deadline:
                # Separate the output before suspended stage generators relinquish
                # native input fields. Tensor storage itself remains shared.
                request.result = PipelineContext(**vars(result)) if borrowed_frame and result is not None else result
            if borrowed_frame and request.input_drained:
                for item in (request.owner, request.item, result):
                    if item is not None and getattr(item, "_decode_buffer", None) is not None:
                        vars(item).pop("frame", None)
                        vars(item).pop("_decode_buffer", None)
                request.input_tensors.clear()
            self.request = None
            request.done.set()

    def release_input(self, request, ready_event, *, frame=False):
        with self.condition:
            if self.request is not request or request.done.is_set():
                return
            if not request.consumed:
                raise RuntimeError("입력을 받은 뒤에만 사용 종료를 알릴 수 있습니다.")
            if ready_event is not None and not callable(getattr(ready_event, "query", None)):
                raise TypeError("ready_event는 query 메서드를 가진 완료 이벤트여야 합니다.")
            if frame:
                request.frame_release_requested = True
                request.frame_release_event = ready_event
            else:
                request.release_requested = True
                request.release_event = ready_event

    def input_released(self, request):
        if request.frame_release_requested:
            return self._event_completed(request.frame_release_event)
        if not request.release_requested:
            return False
        return self._event_completed(request.release_event)

    @staticmethod
    def _event_completed(event):
        if event is None:
            return True
        try:
            return bool(event.query())
        except Exception:
            logger.exception("CudaAsync 원본 사용 종료 이벤트를 확인하지 못해 해당 프레임을 폐기합니다.")
            return False

    def close(self):
        with self.condition:
            self.closed = True
            self.condition.notify_all()


def _close(outputs):
    close = getattr(outputs, "close", None)
    if callable(close):
        try:
            close()
        except Exception:
            logger.exception("CudaAsync 처리 스트림 정리에 실패했습니다.")


class _StageInput(Iterator[PipelineContext]):
    def __init__(self):
        self.item = None
        self.consumed = False

    def __next__(self):
        if self.consumed:
            raise RuntimeError("CudaAsync 단계는 입력마다 정확히 한 번 출력해야 합니다.")
        self.consumed = True
        return self.item


class _Stage(Iterator[PipelineContext]):
    def __init__(self, step, upstream, slot):
        self.step, self.upstream, self.slot = step, upstream, slot
        self.inputs = _StageInput()
        self.outputs = None

    def __next__(self):
        item = next(self.upstream)
        request = self.slot.request
        if isinstance(self.upstream, _Stage) and (request.expired.is_set() or time.monotonic() >= request.deadline):
            return item
        self.inputs.item, self.inputs.consumed = item, False
        try:
            if self.outputs is None:
                self.outputs = iter(self.step.process(self.inputs))
            output = next(self.outputs)
            if not self.inputs.consumed or not isinstance(output, PipelineContext):
                raise RuntimeError("CudaAsync 단계는 입력 하나당 PipelineContext 하나를 출력해야 합니다.")
            return output
        finally:
            self.inputs.item = None

    def close(self):
        _close(self.outputs)
        if isinstance(self.upstream, _Stage):
            self.upstream.close()


class CudaAsync(Step):
    def __init__(self, *steps: Step, timeout_ms: float = 5) -> None:
        if not steps or any(not isinstance(step, Step) for step in steps):
            raise TypeError("Async가 감싸는 객체는 Step이어야 합니다.")
        self._validate_timeout(timeout_ms)
        self.steps = steps
        self.step = steps[0]
        self._hot_steps = tuple(
            step if isinstance(step, Hotswap) or is_embedded_step(step)
            else Hotswap(step, recover_errors=False)
            for step in steps
        )
        self.timeout_ms = timeout_ms
        self._config_defaults = {"timeout_ms": timeout_ms}
        self._session_lock = Lock()

    def __getstate__(self):
        state = vars(self).copy()
        state.pop("_session_lock", None)
        return state

    def __setstate__(self, state):
        vars(self).update(state)
        self._session_lock = Lock()

    @staticmethod
    def _validate_timeout(value):
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or value < 0):
            raise ValueError("timeout_ms는 유한한 0 이상의 숫자여야 합니다.")

    def configure(self, config: SimpleNamespace) -> None:
        config = self._resolve_config(config)
        timeout = getattr(config, "timeout_ms", self.timeout_ms)
        self._validate_timeout(timeout)
        if any(key != "timeout_ms" for key in vars(config)):
            raise ValueError("Async는 timeout_ms만 받습니다. 내부 Step은 최상위 클래스명 섹션으로 설정하세요.")
        self.timeout_ms = timeout

    def _consume(self, slot):
        outputs = None
        model_streams = {}
        last_context = copy_context()
        try:
            while (request := slot.wait()) is not None:
                request.prepared.wait()
                result = None
                last_context = request.context

                def execute():
                    nonlocal outputs
                    for event in request.ready_events:
                        event.synchronize()
                    if request.error is not None:
                        request.input_drained = True
                        return None
                    producer = getattr(request.item, "cuda_stream", None)
                    device = producer.device if producer is not None else next((t.device for t in request.input_tensors if t.is_cuda), None)
                    stream = model_streams.get(device)
                    if device is not None and stream is None:
                        stream = model_streams[device] = torch.cuda.Stream(device=device)
                    try:
                        callback = (lambda event, current=request: slot.release_input(current, event)) if len(self.steps) == 1 else (lambda event: None)
                        frame_callback = lambda event, current=request: slot.release_input(current, event, frame=True)
                        with _input_scope(callback), _frame_scope(frame_callback), _model_stream_scope(stream):
                            with torch.cuda.stream(stream) if stream is not None else nullcontext():
                                if outputs is None:
                                    if len(self.steps) == 1 and not isinstance(self._hot_steps[0], Hotswap):
                                        outputs = iter(self.step.process(slot))
                                    else:
                                        outputs = slot
                                        for step in self._hot_steps:
                                            outputs = _Stage(step, outputs, slot)
                                output = next(outputs)
                    finally:
                        if stream is not None:
                            stream.synchronize()
                        for tensor in request.input_tensors:
                            if tensor.is_cuda:
                                torch.cuda.current_stream(tensor.device).synchronize()
                        request.input_drained = True
                    if not request.consumed or not isinstance(output, PipelineContext):
                        raise RuntimeError("CudaAsync 단계는 입력 하나당 PipelineContext 하나를 출력해야 합니다.")
                    if getattr(output, "_pipeworks_hotswap_epoch", None) == ():
                        del output._pipeworks_hotswap_epoch
                    return output

                try:
                    result = request.context.run(execute)
                except Exception:
                    logger.exception("CudaAsync 처리에 실패하여 원본을 전달합니다.")
                    request.context.run(_close, outputs)
                    outputs = None
                finally:
                    profile = getattr(request.item, "_tensor_rt_profile", None)
                    if profile is not None and not profile.finished:
                        profile.finish("error" if result is None else "partial")
                    slot.finish(request, result)
                request = result = None
        finally:
            last_context.run(_close, outputs)
            slot.close()

    def process(self, inputs: Iterator[PipelineContext]) -> Iterator[PipelineContext]:
        from pipeworks.main import _current_output_writer, _use_output_writer

        slot = _InputSlot()
        worker = None
        acquired = False
        output_writer = _current_output_writer()
        kinds = set()
        for step in self.steps:
            original = step.wrapped_step if isinstance(step, Hotswap) else step
            names = {cls.__name__ for cls in type(original).__mro__}
            if "YoloDetect" in names:
                kinds.add("YOLO")
            elif names & {"TensorRTPreProcess", "TensorRTInference", "TensorRTPostProcess"}:
                kinds.add("TensorRT")

        def consume():
            try:
                with _use_output_writer(output_writer):
                    self._consume(slot)
            finally:
                self._session_lock.release()

        try:
            for item in inputs:
                if not acquired:
                    acquired = self._session_lock.acquire(blocking=False)
                    if not acquired:
                        for kind in kinds:
                            status(kind, "busy")
                        yield item
                        del item
                        continue
                request = _Request(item, time.monotonic() + self.timeout_ms / 1000)
                if slot.offer(request):
                    try:
                        _prepare(request)
                    except Exception as error:
                        request.error = error
                        for kind in kinds:
                            status(kind, "error")
                        logger.exception("CudaAsync 입력 준비에 실패하여 원본을 전달합니다.")
                    request.prepared.set()
                    if worker is None:
                        worker = Thread(target=consume, name="pipeworks-async", daemon=True)
                        try:
                            worker.start()
                        except Exception:
                            worker = None
                            raise
                    slot.publish()
                    request.done.wait(max(0, request.deadline - time.monotonic()))
                    drop_frame = False
                    with slot.condition:
                        if request.done.is_set() and request.result is not None:
                            fields = vars(request.result).copy()
                            vars(item).clear()
                            vars(item).update(fields)
                            del fields
                        else:
                            request.expired.set()
                            if not request.done.is_set() or request.completed_at > request.deadline:
                                for kind in kinds:
                                    status(kind, "timeout")
                            input_finished = request.done.is_set() and request.input_drained
                            drop_frame = not input_finished and not slot.input_released(request)
                        request.result = None
                    if drop_frame:
                        del item
                        request = None
                        continue
                else:
                    for kind in kinds:
                        status(kind, "busy")
                yield item
                del item
                request = None
        finally:
            slot.close()
            if acquired and worker is None:
                self._session_lock.release()
