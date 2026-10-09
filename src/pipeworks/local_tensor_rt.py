"""Shared TensorRT batches with explicit leading batch-axis contracts."""

from collections import deque
from contextvars import copy_context
from dataclasses import dataclass, field
import math
from pathlib import Path
from queue import Queue
from threading import Event, Lock, Thread
import time

import torch
import yaml

from pipeworks.batch_collector import collect_batch
from pipeworks.embedded.tensor_rt_inference import _EngineSession
from pipeworks.detection_profile import Profile, span, use


_workers = {}
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


def _settings(path):
    config_path = path.with_suffix(".yml")
    if not config_path.is_file():
        return 1, 0.0, ()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("TensorRT batch settings must be a mapping.")
    size, timeout, plugins = config.get("max_batch_size", 1), config.get("timeout", 0), config.get("plugins", [])
    if isinstance(size, bool) or not isinstance(size, int) or size < 1:
        raise ValueError("max_batch_size must be a positive integer.")
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout < 0:
        raise ValueError("timeout must be finite nonnegative milliseconds.")
    if not isinstance(plugins, list) or any(not isinstance(p, str) or not p for p in plugins):
        raise ValueError("plugins must be a list of paths.")
    return size, timeout / 1000, tuple(config_path.parent / p for p in plugins)


class _ModelWorker:
    def __init__(self, path):
        self.path = path
        self.size, self.timeout, self.plugins = _settings(path)
        self.requests = Queue()
        self.thread = Thread(target=self._run, name=f"pipeworks-tensorrt-batch-{path.stem}", daemon=True)
        self.thread.start()

    def _run(self):
        deferred = deque()
        sessions, streams = {}, {}
        while True:
            batch = collect_batch(self.requests, deferred, self.size, self.timeout,
                                  key=lambda r: r.key, received_at=lambda r: r.received_at)
            dequeued_at = time.monotonic()
            profile = Profile("TensorRT") if any(r.profile_enabled for r in batch) else None
            scope = use(profile)
            scope.__enter__()
            stream = None
            try:
                gpu_id = batch[0].gpu_id
                if gpu_id not in streams:
                    streams[gpu_id] = torch.cuda.Stream(device=gpu_id)
                stream = streams[gpu_id]
                with torch.cuda.stream(stream), torch.no_grad():
                    with span("input_wait"):
                        for request in batch:
                            request.ready_event.synchronize()
                    with span("input_copy", stream):
                        if isinstance(batch[0].inputs, dict):
                            tensors = {name: torch.cat([r.inputs[name] for r in batch], dim=0) for name in batch[0].inputs}
                        else:
                            tensors = torch.cat([r.inputs for r in batch], dim=0)
                    if gpu_id not in sessions:
                        with span("prepare"):
                            sessions[gpu_id] = _EngineSession(self.path, self.plugins)
                    started = time.perf_counter()
                    # Use an isolated stats context: callers record their own completed requests.
                    from pipeworks.embedded.stream_report import report_scope
                    with report_scope():
                        outputs = sessions[gpu_id].infer(tensors, stream, copy_context())
                    elapsed = time.perf_counter() - started
                    if any(not isinstance(t, torch.Tensor) or not t.is_cuda or t.device != stream.device
                           or t.ndim < 1 or t.shape[0] != len(batch) for t in outputs.values()):
                        raise ValueError("TensorRT outputs must have leading batch axis matching request count.")
                    for index, request in enumerate(batch):
                        own = Profile("TensorRT") if request.profile_enabled else None
                        with use(own), span("output_copy", stream):
                            request.result = {name: t[index:index + 1].clone() for name, t in outputs.items()}
                        request.profile = own
                        request.inference_seconds = elapsed
                    with span("completion_wait"):
                        stream.synchronize()
            except Exception as error:
                for request in batch:
                    request.result = None
                    request.error = f"{type(error).__name__}: {error}"
                session = sessions.pop(batch[0].gpu_id, None)
                try:
                    if stream is not None:
                        stream.synchronize()
                except Exception as cleanup_error:
                    for request in batch:
                        request.error += f"; cleanup: {cleanup_error}"
                finally:
                    if session is not None:
                        try:
                            session.close()
                        except Exception:
                            pass
            finally:
                scope.__exit__(None, None, None)
                tensors = outputs = None
                for request in batch:
                    if request.profile_enabled:
                        own = request.profile or Profile("TensorRT")
                        own.merge(profile)
                        own.add("queue", dequeued_at - request.received_at)
                        request.profile = own
                    request.inputs = request.ready_event = None
                    request.done.set()
                batch = request = None


def infer(model_path: Path, inputs, gpu_id: int = 0, *, ready_event=None, on_inference_complete=None, on_profile_complete=None):
    """Collect batch-one inputs and return batch-one GPU output mappings."""
    path = Path(model_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    if isinstance(gpu_id, bool) or not isinstance(gpu_id, int) or gpu_id < 0:
        raise ValueError("gpu_id must be a nonnegative integer.")
    if isinstance(inputs, torch.Tensor):
        entries = [("", inputs)]
    elif isinstance(inputs, dict) and inputs and all(isinstance(n, str) for n in inputs):
        entries = sorted(inputs.items())
    else:
        raise ValueError("inputs must be a GPU tensor or named GPU tensor mapping.")
    for name, tensor in entries:
        if not isinstance(tensor, torch.Tensor) or not tensor.is_cuda or tensor.device.index != gpu_id or tensor.ndim < 1 or tensor.shape[0] != 1:
            raise ValueError("Each input must be a batch-one GPU tensor matching gpu_id.")
    key = (gpu_id, isinstance(inputs, dict), tuple((n, t.dtype, tuple(t.shape[1:])) for n, t in entries))
    if ready_event is None:
        ready_event = torch.cuda.Event()
        ready_event.record(torch.cuda.current_stream(gpu_id))
    request = _Request(inputs.copy() if isinstance(inputs, dict) else inputs, gpu_id, key, ready_event)
    request.profile_enabled = on_profile_complete is not None
    with _workers_lock:
        worker = _workers.get(path)
        if worker is None:
            worker = _workers[path] = _ModelWorker(path)
    worker.requests.put(request)
    request.done.wait()
    if on_profile_complete is not None and request.profile is not None:
        on_profile_complete(request.profile)
    if request.error is not None:
        raise RuntimeError(request.error)
    if on_inference_complete is not None:
        on_inference_complete(request.inference_seconds)
    return request.result
