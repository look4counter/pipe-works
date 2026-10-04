from types import SimpleNamespace
from pipeworks.models import PipelineContext, Step
from typing import Iterator
import time


class PostProcess(Step):
    def configure(self, config: SimpleNamespace) -> None:
        pass

    def process(self, inputs: Iterator[PipelineContext]) -> Iterator[PipelineContext]:
        for input in inputs:
            # print(f"PostProcess: {input.detections}")
            time.sleep(5)
            yield input
