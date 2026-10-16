
from collections.abc import Iterator
from contextlib import ExitStack
from types import SimpleNamespace

from pipeworks.hotswap import Hotswap, is_embedded_step
from pipeworks.models import PipelineContext, Step
from pipeworks.execution import _DroppedFrame, _frame_drop_scope


class _Input(Iterator[PipelineContext]):
    def __init__(self):
        self.item = None
        self.consumed = False
        self.closed = False

    def __next__(self):
        if self.closed:
            raise StopIteration
        if self.item is None or self.consumed:
            raise RuntimeError("EveryNFrames 내부 Step은 입력마다 정확히 한 번 출력해야 합니다.")
        self.consumed = True
        return self.item


def _close(iterator):
    close = getattr(iterator, "close", None)
    if callable(close):
        close()


class EveryNFrames(Step):
    def __init__(self, *steps: Step, interval_frames: int = 1) -> None:
        if not steps or any(not isinstance(step, Step) for step in steps):
            raise TypeError("EveryNFrames는 하나 이상의 Step을 받아야 합니다.")
        self.steps = steps
        self._hot_steps = tuple(
            step
            if isinstance(step, Hotswap) or is_embedded_step(step)
            else Hotswap(step, recover_errors=False)
            for step in steps
        )
        self._set_config_defaults(interval_frames=interval_frames)

    def configure(self, config: SimpleNamespace) -> None:
        config = self._resolve_config(config)
        if set(vars(config)) != {"interval_frames"}:
            raise ValueError("EveryNFrames는 interval_frames만 받습니다. 내부 Step은 클래스명 섹션으로 설정하세요.")
        interval = config.interval_frames
        if isinstance(interval, bool) or not isinstance(interval, int) or interval < 1:
            raise ValueError("interval_frames는 1 이상의 정수여야 합니다.")
        self.interval_frames = interval

    def process(self, inputs: Iterator[PipelineContext]) -> Iterator[PipelineContext]:
        inputs = iter(inputs)
        slots = [_Input() for _ in self._hot_steps]
        outputs = [None] * len(slots)
        cleanup = ExitStack()
        cleanup.callback(_close, inputs)
        try:
            for index, item in enumerate(inputs):
                if index % self.interval_frames:
                    yield item
                    continue
                for position, step in enumerate(self._hot_steps):
                    slot = slots[position]
                    slot.item, slot.consumed = item, False
                    try:
                        if outputs[position] is None:
                            outputs[position] = iter(step.process(slot))
                            cleanup.callback(_close, outputs[position])
                        try:
                            with _frame_drop_scope():
                                result = next(outputs[position])
                        except StopIteration as error:
                            raise RuntimeError("EveryNFrames 내부 Step에 출력이 없습니다.") from error
                        if not slot.consumed or not isinstance(result, PipelineContext):
                            raise RuntimeError("EveryNFrames 내부 Step은 입력 하나당 PipelineContext 하나를 출력해야 합니다.")
                        if isinstance(result, _DroppedFrame):
                            break
                        item = result
                    finally:
                        slot.item = None
                if isinstance(result, _DroppedFrame):
                    del item, result
                    continue
                yield item
                del item, result
            for slot, output in zip(slots, outputs):
                slot.closed = True
                if output is not None:
                    try:
                        next(output)
                    except StopIteration:
                        pass
                    else:
                        raise RuntimeError("EveryNFrames 내부 Step이 입력보다 많은 출력을 반환했습니다.")
        finally:
            for slot in slots:
                slot.item = None
                slot.closed = True
            cleanup.close()
