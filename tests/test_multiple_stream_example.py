from pathlib import Path
import runpy
import sys
from threading import Barrier, Lock
from unittest import TestCase
from unittest.mock import patch


class MultipleStreamExampleTests(TestCase):
    def test_runs_every_pipeline_concurrently_and_waits_for_completion(self):
        examples = Path(__file__).resolve().parents[1] / "examples"
        with patch.object(sys, "path", [str(examples), *sys.path]):
            module = runpy.run_path(str(examples / "02_multiple_stream_rtsp_style.py"))

        barrier = Barrier(3, timeout=5)
        started = []
        lock = Lock()

        class FakePipeline:
            def __init__(self, video):
                self.video = video

            def run(self):
                with lock:
                    started.append(self.video)
                barrier.wait()

        with patch.dict(module["run_pipelines"].__globals__, {"build_pipeline": FakePipeline}):
            module["run_pipelines"](("one", "two", "three"))

        self.assertCountEqual(started, ("one", "two", "three"))

    def test_propagates_pipeline_error(self):
        examples = Path(__file__).resolve().parents[1] / "examples"
        with patch.object(sys, "path", [str(examples), *sys.path]):
            module = runpy.run_path(str(examples / "02_multiple_stream_rtsp_style.py"))

        class FakePipeline:
            def __init__(self, video):
                self.video = video

            def run(self):
                if self.video == "broken":
                    raise RuntimeError("stream failed")

        with patch.dict(module["run_pipelines"].__globals__, {"build_pipeline": FakePipeline}):
            with self.assertRaisesRegex(RuntimeError, "stream failed"):
                module["run_pipelines"](("ok", "broken"))
