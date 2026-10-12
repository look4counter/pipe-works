"""Shared GPU batch execution for caller-prepared model inputs."""

import math
import time
from collections import deque
from contextvars import copy_context
from dataclasses import dataclass, field
from queue import Queue
from threading import Event, Lock, Thread

import torch

from pipeworks.embedded.yolo_report import Profile, span, use, backend_kind
from pipeworks.embedded.stream_report import report_scope
from pipeworks.embedded.yolo_inference import _Session, _validate_input
from pipeworks.backend import Backend
from pipeworks.batch_collector import collect_batch
from pipeworks.model_worker import get_model_worker
from pipeworks.yolo_backend import (
    batch_settings, concatenate_inputs, input_signature, validate_backend, validate_gpu,
)
from pipeworks.yolo_backends.tensorrt import (
    _EngineSession, _engine_settings, _load_model_config, _validate_profile_index,
)

_workers = {}
_worker_paths = {}
_workers_lock = Lock()


@dataclass
class _Request:
    inputs: object
    gpu_id: int
    key: tuple
    ready_event: object
    received_at: float = field(default_factory=time.monotonic)
    done: Event = field(default_factory=Event)
    result: object = None
    error: str | None = None
    inference_seconds: float | None = None
    profile_enabled: bool = False
    profile: object = None
    backend: str = "torchscript"
    profile_index: int = 0


def _settings(path):
    config = _load_model_config(path)
    plugins = _engine_settings(path, config)
    size, timeout = config.get("max_batch_size", 1), config.get("timeout_ms", 0)
    if isinstance(size, bool) or not isinstance(size, int) or size < 1:
        raise ValueError("max_batch_size must be a positive integer.")
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not math.isfinite(timeout)
        or timeout < 0
    ):
        raise ValueError("timeout_ms must be finite nonnegative milliseconds.")
    return size, timeout / 1000, plugins


class _ModelWorker:
    def __init__(self, path, backend="torchscript"):
        self.path = path
        self.backend = backend
        self.plugins = ()
        if backend == Backend.TENSORRT:
            self.size, self.timeout, self.plugins = _settings(path)
        else:
            self.size, self.timeout = batch_settings(path)
        self.requests = Queue()
        self.thread = Thread(
            target=self._run,
            name=f"pipeworks-yolo-inference-{path.stem}",
            daemon=True,
        )
        self.thread.start()

    def _run(self):
        deferred = deque()
        sessions, streams = {}, {}
        kind = backend_kind(self.backend)
        while True:
            batch = collect_batch(
                self.requests, deferred, self.size, self.timeout,
                key=lambda r: r.key,
                received_at=lambda r: r.received_at,
            )
            dequeued_at = time.monotonic()
            profile = Profile(kind) if any(r.profile_enabled for r in batch) else None
            stream = tensors = outputs = None
            first = batch[0]
            session_key = first.gpu_id, first.profile_index
            try:
                with use(profile):
                    if first.gpu_id not in streams:
                        streams[first.gpu_id] = torch.cuda.Stream(device=first.gpu_id)
                    stream = streams[first.gpu_id]
                    with torch.cuda.stream(stream), torch.no_grad():
                        with span("input_wait"):
                            for request in batch:
                                if request.ready_event is not None:
                                    stream.wait_event(request.ready_event)
                        if session_key not in sessions:
                            with span("prepare"):
                                if self.backend == Backend.TENSORRT:
                                    session = _EngineSession(
                                        self.path, self.plugins, first.profile_index
                                    )
                                else:
                                    session = _Session(self.path, first.gpu_id, self.backend)
                                sessions[session_key] = session
                        with span("input_copy", stream):
                            tensors = concatenate_inputs([r.inputs for r in batch])
                        started = time.perf_counter()
                        if self.backend == Backend.TENSORRT:
                            # Callers record completed requests in their own report scopes.
                            with report_scope():
                                outputs = sessions[session_key].infer(
                                    tensors, stream, copy_context()
                                )
                        else:
                            outputs = sessions[session_key].infer(tensors, stream)
                        for name, output in outputs.items():
                            if not isinstance(output, torch.Tensor):
                                raise ValueError("공유 배치 출력은 GPU 텐서여야 합니다.")
                            validate_gpu(output, first.gpu_id)
                            if output.ndim < 1 or output.shape[0] != len(batch):
                                raise ValueError(
                                    f"공유 배치 출력의 첫 축이 요청 수와 다릅니다 (batch axis): {name}"
                                )
                        for index, request in enumerate(batch):
                            own = Profile(kind) if request.profile_enabled else None
                            with use(own), span("output_copy", stream):
                                request.result = {
                                    name: output[index : index + 1].clone()
                                    for name, output in outputs.items()
                                }
                            request.profile = own
                        with span("completion_wait"):
                            stream.synchronize()
                        elapsed = time.perf_counter() - started
                        for request in batch:
                            request.inference_seconds = elapsed
            except Exception as error:  # noqa: BLE001 -- wake every waiting request
                message = f"{type(error).__name__}: {error}"
                session = sessions.pop(session_key, None)
                try:
                    if stream is not None:
                        stream.synchronize()
                except Exception as cleanup_error:  # noqa: BLE001 -- preserve original failure
                    message += f"; cleanup: {cleanup_error}"
                finally:
                    close = getattr(session, "close", None)
                    if callable(close):
                        try:
                            close()
                        except Exception:  # noqa: BLE001 -- original failure already retained
                            pass
                for request in batch:
                    request.result = None
                    request.error = message
            finally:
                for request in batch:
                    if request.profile_enabled:
                        own = request.profile or Profile(kind)
                        own.merge(profile)
                        own.add("queue", dequeued_at - request.received_at)
                        request.profile = own
                    request.inputs = request.ready_event = None
                    request.done.set()
                # Do not retain caller tensors or evicted sessions while idle.
                batch = first = request = tensors = outputs = session = None


def _worker(model_path, backend):
    # Separate path aliases and canonical caches for each execution backend.
    with _workers_lock:
        workers = _workers.setdefault(backend, {})
        paths = _worker_paths.setdefault(backend, {})
    return get_model_worker(
        model_path,
        workers,
        paths,
        _workers_lock,
        lambda path: _ModelWorker(path, backend),
    )


def infer(
    model_path,
    inputs,
    gpu_id=0,
    *,
    backend="torchscript",
    profile_index=0,
    ready_event=None,
    on_inference_complete=None,
    on_profile_complete=None,
):
    if isinstance(gpu_id, bool) or not isinstance(gpu_id, int) or gpu_id < 0:
        raise ValueError("gpu_id는 음수가 아닌 정수여야 합니다.")
    _validate_input(inputs, gpu_id, batch=True)
    validate_backend(backend)
    _validate_profile_index(profile_index)
    if backend != Backend.TENSORRT and profile_index != 0:
        raise ValueError("profile_index는 TensorRT 실행부에서만 지정할 수 있습니다.")
    key = backend, gpu_id, profile_index, input_signature(inputs)
    if ready_event is None:
        ready_event = torch.cuda.Event()
        ready_event.record(torch.cuda.current_stream(gpu_id))
    request = _Request(
        inputs, gpu_id, key, ready_event, backend=backend, profile_index=profile_index
    )
    request.profile_enabled = on_profile_complete is not None
    worker = _worker(model_path, backend)
    worker.requests.put(request)
    request.done.wait()
    if on_profile_complete is not None and request.profile is not None:
        on_profile_complete(request.profile)
    if request.error is not None:
        raise RuntimeError(request.error)
    if on_inference_complete is not None:
        on_inference_complete(request.inference_seconds)
    return request.result

