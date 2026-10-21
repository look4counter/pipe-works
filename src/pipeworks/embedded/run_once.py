from collections.abc import Iterator
from types import SimpleNamespace

from pipeworks.hotswap import Hotswap, is_embedded_step
from pipeworks.models import PipelineContext, Step


class RunOnce(Step):
    """내부 Step을 인스턴스 수명 동안 최초 입력에 대해서만 실행한다."""

    def __init__(self, step: Step) -> None:
        if not isinstance(step, Step):
            raise TypeError("RunOnce는 Step을 하나 받아야 합니다.")
        self.step = step
        wrapped = (
            step
            if isinstance(step, Hotswap) or is_embedded_step(step)
            else Hotswap(step, recover_errors=False)
        )
        self._hot_steps = (wrapped,)
        self._ran = False
        self._set_config_defaults()

    def configure(self, config: SimpleNamespace) -> None:
        config = self._resolve_config(config)
        if vars(config):
            raise ValueError("RunOnce는 별도 설정을 받지 않습니다. 내부 Step을 클래스명 섹션으로 설정하세요.")

    def process(self, inputs: Iterator[PipelineContext]) -> Iterator[PipelineContext]:
        inputs = iter(inputs)
        if self._ran:
            yield from inputs
            return

        try:
            first = next(inputs)
        except StopIteration:
            return

        yield from self._hot_steps[0].process(iter((first,)))
        self._ran = True
        yield from inputs
