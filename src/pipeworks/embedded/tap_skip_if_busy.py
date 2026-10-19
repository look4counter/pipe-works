import logging
from pipeworks.embedded.recovery import is_fatal, close
from contextvars import copy_context
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
        self.consumed = 0

    def offer(self, item: PipelineContext) -> bool:
        with self._condition:
            if self._closed or self._busy:
                return False
            # 분기별 속성과 핫스왑 정보는 격리하고 영상·자원 참조는 공유한다.
            self._pending = PipelineContext(**vars(item))
            self._busy = True
            self._condition.notify()
            return True

    def __next__(self) -> PipelineContext:
        with self._condition:
            if self._busy and self._pending is _EMPTY:
                self._busy = False
            while self._pending is _EMPTY:
                if self._closed:
                    raise StopIteration
                self._condition.wait()
            self.consumed += 1
            item = self._pending
            self._pending = _EMPTY
            return item

    def close(self) -> None:
        with self._condition:
            self._closed = True
            self._condition.notify_all()


class TapSkipIfBusy(Step):
    def __init__(self, step: Step) -> None:
        self.step = (
            step
            if isinstance(step, Hotswap) or is_embedded_step(step)
            else Hotswap(step, recover_errors=False)
        )

    def configure(self, config: SimpleNamespace) -> None:
        self.step.configure(config)

    def process(self, inputs: Iterator[PipelineContext]) -> Iterator[PipelineContext]:
        from pipeworks.main import _current_output_writer, _use_output_writer

        slot = _InputSlot()
        output_writer = _current_output_writer()
        context = copy_context()
        failures = []

        def consume() -> None:
            with _use_output_writer(output_writer):
                while not slot._closed:
                    consumed = slot.consumed
                    outputs = None
                    try:
                        outputs = iter(self.step.process(slot))
                        for completed in outputs:
                            del completed
                    except Exception as error:
                        if is_fatal(error):
                            failures.append(error)
                            slot.close()
                            return
                        logger.warning("TapSkipIfBusy 작업을 재생성합니다: %s", error)
                        if consumed == slot.consumed:
                            try:
                                next(slot)
                            except StopIteration:
                                return
                    else:
                        return
                    finally:
                        try:
                            close(outputs)
                        except Exception as error:
                            failures.append(error)
                            slot.close()


        worker = Thread(
            target=context.run, args=(consume,), name="pipeworks-tap-skip-if-busy", daemon=True
        )
        worker.start()
        exhausted = False
        try:
            for item in inputs:
                if failures:
                    raise failures[0]
                slot.offer(item)
                yield item
            exhausted = True
        finally:
            slot.close()
            if exhausted:
                worker.join()
                if failures:
                    raise failures[0]
