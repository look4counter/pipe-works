from abc import ABC, abstractmethod
from types import SimpleNamespace
from typing import Iterator


class PipelineContext(SimpleNamespace):
    pass


class Step(ABC):
    def configure(self, config: SimpleNamespace) -> None:
        pass

    @abstractmethod
    def process(
        self, inputs: Iterator[PipelineContext]
    ) -> Iterator[PipelineContext]: ...
