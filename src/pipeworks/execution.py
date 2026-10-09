"""Optional signals scoped to the currently executing asynchronous request."""

from contextlib import contextmanager
from contextvars import ContextVar


_input_release = ContextVar("pipeworks_input_release", default=None)
_frame_release = ContextVar("pipeworks_frame_release", default=None)
_model_stream = ContextVar("pipeworks_model_stream", default=None)


def current_model_stream():
    return _model_stream.get()


@contextmanager
def _model_stream_scope(stream):
    token = _model_stream.set(stream)
    try:
        yield
    finally:
        _model_stream.reset(token)


def release_input(*, ready_event=None) -> None:
    """Promise no further shared-input access, optionally after a CUDA event.

    Outside an CudaAsync request this is a no-op. Result attributes may still be
    assigned to the working context, but its shared data must not be used again.
    """
    callback = _input_release.get()
    if callback is not None:
        callback(ready_event)


def release_frame(*, ready_event=None) -> None:
    """Promise no further original-frame reads in this CudaAsync chain.

    RGB/model tensors created by preprocessing may still be used. A CUDA event
    must cover every submitted original-frame read. Outside a request this is
    a no-op; later wrapped Steps must also honor the promise.
    """
    callback = _frame_release.get()
    if callback is not None:
        callback(ready_event)


@contextmanager
def _frame_scope(callback):
    token = _frame_release.set(callback)
    try:
        yield
    finally:
        _frame_release.reset(token)


@contextmanager
def _input_scope(callback):
    token = _input_release.set(callback)
    try:
        yield
    finally:
        _input_release.reset(token)
