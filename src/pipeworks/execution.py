"""Optional signals scoped to the currently executing asynchronous request."""

from contextlib import contextmanager
from contextvars import ContextVar


_input_release = ContextVar("pipeworks_input_release", default=None)


def release_input(*, ready_event=None) -> None:
    """Promise no further shared-input access, optionally after a CUDA event.

    Outside an CudaAsync request this is a no-op. Result attributes may still be
    assigned to the working context, but its shared data must not be used again.
    """
    callback = _input_release.get()
    if callback is not None:
        callback(ready_event)


@contextmanager
def _input_scope(callback):
    token = _input_release.set(callback)
    try:
        yield
    finally:
        _input_release.reset(token)
