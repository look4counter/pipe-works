from abc import ABC, abstractmethod
from copy import deepcopy
from types import SimpleNamespace
from typing import Iterator


class PipelineContext(SimpleNamespace):
    pass


class Step(ABC):
    def _set_config_defaults(self, **defaults) -> None:
        self._config_defaults = deepcopy(defaults)
        self.configure(SimpleNamespace())

    def _resolve_config(self, config: SimpleNamespace) -> SimpleNamespace:
        defaults = deepcopy(self._config_defaults)
        return SimpleNamespace(**(defaults | vars(config)))

    @abstractmethod
    def configure(self, config: SimpleNamespace) -> None:
        pass

    @abstractmethod
    def process(
        self, inputs: Iterator[PipelineContext]
    ) -> Iterator[PipelineContext]: ...
