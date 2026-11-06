import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from pipeworks import Pipeline
from pipeworks.embedded import CudaAsync, EveryNFrames, TapSkipIfBusy, YoloInference
from pipeworks.hotswap import Hotswap
from pipeworks.models import PipelineContext, Step


class PidSource(Step):
    def __init__(self, seen):
        self.seen = seen

    def configure(self, config):
        pass

    def __getstate__(self):
        raise TypeError("must execute without serialization")

    def process(self, inputs):
        self.seen.append(os.getpid())
        yield PipelineContext()


class PipelineRoutingTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.config = Path(temporary.name) / "stream.yml"
        self.config.write_text("{}", encoding="utf-8")

    def inference(self, batch=False):
        return YoloInference(Path("model.pt"), backend="torchscript", batch=batch)

    def test_server_runner_keeps_pid_without_requesting_another_server(self):
        seen = []
        pipeline = Pipeline("local", config=self.config).step(PidSource(seen))
        with patch("pipeworks.main.run_remote") as remote:
            pipeline._run_local()
        remote.assert_not_called()
        self.assertEqual(seen, [os.getpid()])

    def test_empty_and_nonbatch_pipelines_use_remote_runner(self):
        for batch_server in ("production", "camera-a"):
            for steps in ([], [self.inference()], [CudaAsync(self.inference())]):
                with self.subTest(batch_server=batch_server, steps=steps):
                    pipeline = Pipeline("remote", config=self.config, batch_server=batch_server)
                    for step in steps:
                        pipeline.step(step)
                    with patch.object(pipeline, "_run_local") as local, patch("pipeworks.main.run_remote") as remote:
                        pipeline.run()
                    local.assert_not_called()
                    remote.assert_called_once_with(pipeline)
                    self.assertEqual(pipeline.batch_server, batch_server)

    def test_each_batch_mode_inside_wrappers_and_mixed_steps_uses_remote(self):
        factories = [
            lambda step: step,
            lambda step: Hotswap(step, watch_code=False),
            lambda step: CudaAsync(step),
            lambda step: EveryNFrames(step),
            lambda step: TapSkipIfBusy(step),
            lambda step: EveryNFrames(CudaAsync(Hotswap(step, watch_code=False))),
            lambda step: TapSkipIfBusy(EveryNFrames(CudaAsync(step))),
        ]
        for batch_server in ("production", "camera-a"):
            for batch in (False, True):
                for factory in factories:
                    with self.subTest(batch_server=batch_server, batch=batch, factory=factory):
                        pipeline = Pipeline("batch", config=self.config, batch_server=batch_server)
                        inference = self.inference(batch)
                        pipeline.step(self.inference()).step(factory(inference))
                        with patch.object(pipeline, "_run_local") as local, patch("pipeworks.main.run_remote") as remote:
                            pipeline.run()
                        remote.assert_called_once_with(pipeline)
                        local.assert_not_called()
                        self.assertEqual(inference.batch, batch)

    def test_repeated_and_cyclic_wrappers_do_not_recurse_forever(self):
        wrapper = Hotswap(self.inference(), watch_code=False)
        wrapper.wrapped_step = wrapper
        pipeline = Pipeline("cycle", config=self.config)
        pipeline.steps = [wrapper, wrapper]
        with patch.object(pipeline, "_run_local") as local, patch("pipeworks.main.run_remote") as remote:
            pipeline.run()
        local.assert_not_called()
        remote.assert_called_once_with(pipeline)

    def test_remote_error_is_propagated_without_local_fallback(self):
        pipeline = Pipeline("error", config=self.config)
        with patch.object(pipeline, "_run_local") as local, patch("pipeworks.main.run_remote", side_effect=RuntimeError("remote error")) as remote:
            with self.assertRaisesRegex(RuntimeError, "remote error"):
                pipeline.run()
        remote.assert_called_once_with(pipeline)
        local.assert_not_called()


if __name__ == "__main__":
    unittest.main()
