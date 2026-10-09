import logging
from threading import Condition, Thread
from types import SimpleNamespace
from typing import Iterator

from pipeworks.hotswap import Hotswap, is_embedded_step
from pipeworks.models import PipelineContext, Step


logger = logging.getLogger(__name__)
_EMPTY = object()


class _InputSlot(Iterator[PipelineContext]):
    def __init__(self) -> None:
        self._condition = Condition()
        self._pending: PipelineContext | object = _EMPTY
        self._busy = False
        self._closed = False

    def offer(self, item: PipelineContext) -> bool:
        with self._condition:
            if self._closed or self._busy:
                return False
            self._pending = item
            self._busy = True
            self._condition.notify()
            return True

    def __next__(self) -> PipelineContext:
        with self._condition:
            # The wrapped Step has finished with the preceding item when it
            # requests another one.
            if self._busy and self._pending is _EMPTY:
                self._busy = False
            while self._pending is _EMPTY:
                if self._closed:
                    raise StopIteration
                self._condition.wait()
            item = self._pending
            self._pending = _EMPTY
            return item

    def close(self) -> None:
        with self._condition:
            self._closed = True
            self._condition.notify_all()


class Tap(Step):
    def __init__(self, step: Step) -> None:
        self.step = step if isinstance(step, Hotswap) or is_embedded_step(step) else Hotswap(step)

    def configure(self, config: SimpleNamespace) -> None:
        self.step.configure(config)

    def process(self, inputs: Iterator[PipelineContext]) -> Iterator[PipelineContext]:
        from pipeworks.main import _current_output_writer, _use_output_writer

        slot = _InputSlot()
        output_writer = _current_output_writer()

        def consume() -> None:
            with _use_output_writer(output_writer):
                try:
                    outputs = iter(self.step.process(slot))
                    try:
                        for _ in outputs:
                            pass
                    finally:
                        close = getattr(outputs, "close", None)
                        if callable(close):
                            close()
                except Exception:
                    logger.exception("Tap 작업이 실패했습니다.")
                finally:
                    slot.close()

        worker = Thread(target=consume, name="pipeworks-tap", daemon=True)
        worker.start()
        exhausted = False
        try:
            for item in inputs:
                slot.offer(item)
                yield item
            exhausted = True
        finally:
            slot.close()
            if exhausted:
                worker.join()
