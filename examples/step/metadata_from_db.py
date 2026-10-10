from types import SimpleNamespace
from pipeworks.models import PipelineContext, Step
from typing import Iterator
from threading import Event, Thread


class MetadataFromDB(Step):

    def configure(self, config: SimpleNamespace) -> None:
        pass

    def process(self, inputs: Iterator[PipelineContext]) -> Iterator[PipelineContext]:
        self.metadata = SimpleNamespace(count=0)
        stop = Event()

        def worker():
            while not stop.wait(3):
                self.metadata.count += 1

        thread = Thread(target=worker, daemon=True)
        thread.start()

        try:
            for input in inputs:
                # print(self.metadata.count)
                yield input
        finally:
            stop.set()
            thread.join()
