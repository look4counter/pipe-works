
from contextlib import contextmanager
from contextvars import ContextVar

from pipeworks.models import PipelineContext


_input_release = ContextVar("pipeworks_input_release", default=None)
_frame_release = ContextVar("pipeworks_frame_release", default=None)
_source_cancel = ContextVar("pipeworks_source_cancel", default=None)
_frame_drop_enabled = ContextVar("pipeworks_frame_drop_enabled", default=False)


class _DroppedFrame(PipelineContext):
    pass


def _can_signal_frame_drop():
    return _frame_drop_enabled.get()


@contextmanager
def _frame_drop_scope():
    token = _frame_drop_enabled.set(True)
    try:
        yield
    finally:
        _frame_drop_enabled.reset(token)


def current_source_cancel():
    return _source_cancel.get()


@contextmanager
def _source_cancel_scope(cancel):
    token = _source_cancel.set(cancel)
    try:
        yield
    finally:
        _source_cancel.reset(token)


def release_input(*, ready_event=None) -> None:
    callback = _input_release.get()
    if callback is not None:
        callback(ready_event)


def release_frame(*, ready_event=None) -> None:
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
