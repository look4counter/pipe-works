"""Run a Step with shared read-only inputs and copy only on timeout."""

from contextlib import nullcontext
from contextvars import Context, copy_context
from copy import deepcopy
from dataclasses import dataclass, field
import logging
import math
from threading import Condition, Event, Lock, Thread
import time
from types import SimpleNamespace
from typing import Iterator

import torch

from pipeworks.models import PipelineContext, Step


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


def _snapshot(request):
    """Copy the retained input for downstream use after the deadline."""
    source = request.owner
    shared = {id(getattr(source, name)): getattr(source, name)
              for name in _SHARED_FIELDS if hasattr(source, name)}
    streams = {}
    try:
        for event in request.ready_events:
            event.synchronize()
        fields = vars(source).copy()
        tensors = {}
        _tensors(fields, tensors, set(shared))
        # Validate and copy CPU objects before launching any GPU copies.
        memo = {**shared, **tensors}
        prepared = deepcopy(PipelineContext(**fields), memo)
        copies = {}
        with torch.no_grad():
            for identity, tensor in tensors.items():
                copy_stream = None
                if tensor.is_cuda:
                    copy_stream = streams.get(tensor.device)
                    if copy_stream is None:
                        copy_stream = torch.cuda.Stream(device=tensor.device)
                        streams[tensor.device] = copy_stream
                with torch.cuda.stream(copy_stream) if copy_stream is not None else nullcontext():
                    copied = tensor.clone()
                    copies[identity] = copied
        return deepcopy(prepared, {**shared, **copies})
    finally:
        for copy_stream in streams.values():
            # Downstream must receive completed copies, independent of the worker.
            copy_stream.synchronize()


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
                raise RuntimeError("Async 단계는 출력 전에 추가 입력을 요구할 수 없습니다.")
            if request.consumed:
                raise RuntimeError("Async 단계는 입력마다 정확히 한 번 출력해야 합니다.")
            request.consumed = True
            return request.item

    def finish(self, request, result):
        with self.condition:
            request.completed_at = time.monotonic()
            if not self.closed and not request.expired.is_set() and request.completed_at <= request.deadline:
                request.result = result
            # Keep storage alive for a caller still making its timeout copy.
            self.request = None
            request.done.set()

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
            logger.exception("Async 처리 스트림 정리에 실패했습니다.")


class Async(Step):
    def __init__(self, step: Step, *, timeout_ms: float = 5) -> None:
        if not isinstance(step, Step):
            raise TypeError("Async가 감싸는 객체는 Step이어야 합니다.")
        self._validate_timeout(timeout_ms)
        self.step = step
        self.timeout_ms = timeout_ms
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
        timeout = getattr(config, "timeout_ms", self.timeout_ms)
        self._validate_timeout(timeout)
        settings = getattr(config, "step", None)
        if hasattr(config, "step") and not isinstance(settings, dict):
            raise ValueError("Async의 step 설정은 매핑이어야 합니다.")
        if settings is None:
            settings = {key: value for key, value in vars(config).items() if key != "timeout_ms"}
        self.step.configure(SimpleNamespace(**settings))
        self.timeout_ms = timeout

    def _consume(self, slot):
        outputs = None
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
                        return None
                    if outputs is None:
                        outputs = iter(self.step.process(slot))
                    stream = getattr(request.item, "cuda_stream", None)
                    try:
                        with torch.cuda.stream(stream) if stream is not None else nullcontext():
                            output = next(outputs)
                    finally:
                        if stream is not None:
                            stream.synchronize()
                        for tensor in request.input_tensors:
                            if tensor.is_cuda:
                                torch.cuda.current_stream(tensor.device).synchronize()
                    if not request.consumed or not isinstance(output, PipelineContext):
                        raise RuntimeError("Async 단계는 입력 하나당 PipelineContext 하나를 출력해야 합니다.")
                    return output

                try:
                    result = request.context.run(execute)
                except Exception:
                    logger.exception("Async 처리에 실패하여 원본을 전달합니다.")
                    request.context.run(_close, outputs)
                    outputs = None
                finally:
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
                        yield item
                        continue
                request = _Request(item, time.monotonic() + self.timeout_ms / 1000)
                if slot.offer(request):
                    try:
                        _prepare(request)
                    except Exception as error:
                        request.error = error
                        logger.exception("Async 입력 준비에 실패하여 원본을 전달합니다.")
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
                    timed_out = False
                    with slot.condition:
                        if request.done.is_set() and request.result is not None:
                            fields = vars(request.result).copy()
                            vars(item).clear()
                            vars(item).update(fields)
                        else:
                            request.expired.set()
                            timed_out = not request.done.is_set() or (
                                request.completed_at is not None and request.completed_at > request.deadline
                            )
                        request.result = None
                    if timed_out:
                        try:
                            fallback = _snapshot(request)
                            vars(item).clear()
                            vars(item).update(vars(fallback))
                        except Exception:
                            logger.exception("Async 시간 초과 복사에 실패하여 작업 완료를 기다립니다.")
                            request.done.wait()
                yield item
        finally:
            slot.close()
            if acquired and worker is None:
                self._session_lock.release()
