from types import SimpleNamespace
from typing import Iterator

from pipeworks.models import PipelineContext, Step


class DropFrames(Step):
    def __init__(self, *, keep_every: int = 1) -> None:
        self._set_config_defaults(keep_every=keep_every)

    def configure(self, config: SimpleNamespace) -> None:
        config = self._resolve_config(config)
        keep_every = config.keep_every
        if isinstance(keep_every, bool) or not isinstance(keep_every, int) or keep_every < 1:
            raise ValueError("DropFrames의 keep_every는 1 이상의 정수여야 합니다.")
        self.keep_every = keep_every

    def process(self, inputs: Iterator[PipelineContext]) -> Iterator[PipelineContext]:
        for index, item in enumerate(inputs):
            if index % self.keep_every == 0:
                yield item
