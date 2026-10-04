from types import SimpleNamespace
from pipeworks.models import PipelineContext, Step
from typing import Iterator
import time
from threading import Thread


class MetadataFromDB(Step):

    def configure(self, config: SimpleNamespace) -> None:
        pass

    def process(self, inputs: Iterator[PipelineContext]) -> Iterator[PipelineContext]:
        self.metadata = SimpleNamespace(count=0)

        def worker():
            while True:
                time.sleep(3)
                self.metadata.count += 1

        thread = Thread(target=worker, daemon=True)
        thread.start()

        for input in inputs:
            # print(self.metadata.count)
            yield input
