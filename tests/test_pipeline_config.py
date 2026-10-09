import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pipeworks import Pipeline
from pipeworks.embedded import NvidiaDecode, RTSPSource, Tap
from pipeworks.models import PipelineContext, Step


class EditingSource(Step):
    def __init__(self, config_path: Path, changes: list[str]):
        self.config_path = config_path
        self.changes = changes

    def process(self, inputs):
        for index in range(len(self.changes) + 1):
            yield PipelineContext(value=index + 1)
            if index < len(self.changes):
                self.config_path.write_text(self.changes[index], encoding="utf-8")
                time.sleep(0.6)


class ConfiguredValue(Step):
    def __init__(self):
        self.generation = 0

    def configure(self, config: SimpleNamespace) -> None:
        self.offset = getattr(config, "offset", 0)
        if self.offset < 0:
            raise ValueError("negative offset")

    def process(self, inputs):
        for item in inputs:
            self.generation += 1
            yield PipelineContext(value=item.value + self.offset, generation=self.generation)


class CollectValues(Step):
    def __init__(self, seen):
        self.seen = seen

    def process(self, inputs):
        for item in inputs:
            self.seen.append((item.value, item.generation))
            yield item


class ConfiguredSource(Step):
    def configure(self, config):
        self.value = config.value

    def process(self, inputs):
        yield PipelineContext(value=self.value)
        yield PipelineContext(value=self.value)


class ChangeAfterFirst(Step):
    def __init__(self, path, seen):
        self.path = path
        self.seen = seen

    def process(self, inputs):
        for item in inputs:
            self.seen.append(item.value)
            if len(self.seen) == 1:
                self.path.write_text("ConfiguredSource:\n  value: 20\n", encoding="utf-8")
                time.sleep(0.6)
            yield item


class RecordingTap(Step):
    def __init__(self, seen):
        self.seen = seen

    def configure(self, config):
        self.offset = getattr(config, "offset", 0)

    def process(self, inputs):
        for item in inputs:
            self.seen.append(item.value + self.offset)
        yield from ()


class TapEditingSource(Step):
    def __init__(self, path, seen):
        self.path = path
        self.seen = seen

    def process(self, inputs):
        yield PipelineContext(value=1)
        deadline = time.monotonic() + 5
        while not self.seen and time.monotonic() < deadline:
            time.sleep(0.01)
        self.path.write_text("Tap:\n  offset: 20\n", encoding="utf-8")
        time.sleep(0.6)
        yield PipelineContext(value=2)


class IdentityStep(Step):
    def __init__(self, starts, configures):
        self.starts = starts
        self.configures = configures

    def configure(self, config):
        self.configures.append(id(self))
        self.offset = config.offset

    def process(self, inputs):
        self.starts.append(id(self))
        for item in inputs:
            yield PipelineContext(value=item.value + self.offset, step_id=id(self))


class IdentityCollector(Step):
    def __init__(self, seen):
        self.seen = seen

    def process(self, inputs):
        for item in inputs:
            self.seen.append((item.value, item.step_id))
            yield item


class PipelineConfigTests(unittest.TestCase):
    def test_config_change_keeps_step_instance_and_running_iterator(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.yaml"
            path.write_text("IdentityStep:\n  offset: 10\n", encoding="utf-8")
            starts = []
            configures = []
            seen = []
            step = IdentityStep(starts, configures)
            pipeline = (Pipeline("in-place-config", config=path)
                        .step(EditingSource(path, ["IdentityStep:\n  offset: 20\n"]))
                        .step(step)
                        .step(IdentityCollector(seen)))
            pipeline._run_local()
            self.assertIs(pipeline.steps[1].wrapped_step, step)
            self.assertEqual(starts, [id(step)])
            self.assertEqual(configures, [id(step), id(step)])
            self.assertEqual(seen, [(11, id(step)), (22, id(step))])

    def test_source_uses_updated_config_on_next_output_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.yaml"
            path.write_text("ConfiguredSource:\n  value: 10\n", encoding="utf-8")
            seen = []
            pipeline = (Pipeline("source-config", config=path)
                        .step(ConfiguredSource())
                        .step(ChangeAfterFirst(path, seen)))
            pipeline._run_local()
            self.assertEqual(seen, [10, 20])

    def test_tap_child_uses_updated_config(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.yaml"
            path.write_text("Tap:\n  offset: 10\n", encoding="utf-8")
            seen = []
            pipeline = (Pipeline("sink-config", config=path)
                        .step(TapEditingSource(path, seen))
                        .step(Tap(RecordingTap(seen))))
            pipeline._run_local()
            self.assertEqual(seen, [11, 22])

    def test_embedded_step_reconfigures_only_after_its_section_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.yaml"
            path.write_text("ConfiguredValue:\n  offset: 10\n", encoding="utf-8")
            seen = []
            changes = ["Other:\n  value: 1\nConfiguredValue:\n  offset: 10\n",
                       "ConfiguredValue:\n  offset: 20\n"]
            with patch("pipeworks.pipeline.is_embedded_step", side_effect=lambda step: isinstance(step, ConfiguredValue)):
                pipeline = (Pipeline("embedded-config", config=path)
                            .step(EditingSource(path, changes))
                            .step(ConfiguredValue())
                            .step(CollectValues(seen)))
                self.assertIsInstance(pipeline.steps[1], ConfiguredValue)
                pipeline._run_local()
            self.assertEqual(seen, [(11, 1), (12, 2), (23, 3)])

    def test_running_pipeline_applies_only_changed_valid_step_sections(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.yaml"
            initial = "ConfiguredValue:\n  offset: 10\n"
            path.write_text(initial, encoding="utf-8")
            changes = [
                initial + "Unrelated:\n  value: 1\n",
                "ConfiguredValue:\n  offset: 20\nUnrelated:\n  value: 1\n",
                "ConfiguredValue: [invalid]\n",
                "ConfiguredValue:\n  offset: -1\n",
                "ConfiguredValue:\n  offset: 30\n",
            ]
            seen = []
            pipeline = (Pipeline("config-reload", config=path)
                        .step(EditingSource(path, changes))
                        .step(ConfiguredValue())
                        .step(CollectValues(seen)))
            pipeline._run_local()
            self.assertEqual(seen, [(11, 1), (12, 2), (23, 3), (24, 4), (25, 5), (36, 6)])

    def test_invalid_unregistered_section_fails_at_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.yaml"
            for content in ("[]\n", "NvidiaDecode: []\n", "RTSPSource: null\n"):
                with self.subTest(content=content):
                    path.write_text(content, encoding="utf-8")
                    with self.assertRaises(ValueError):
                        Pipeline("test", config=path)

    def test_registered_steps_apply_configuration_to_explicit_attributes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.yaml"
            path.write_text("RTSPSource:\n  reconnect_interval: 7\nNvidiaDecode:\n  mode: fast\n", encoding="utf-8")
            source = RTSPSource("rtsp://example")
            decode = NvidiaDecode()
            Pipeline("test", config=path).step(source).step(decode)
        self.assertEqual(source.reconnect_interval, 7)
        self.assertEqual(decode.gpu_id, 0)
        self.assertNotIn("config", vars(source))
        self.assertNotIn("config", vars(decode))


if __name__ == "__main__":
    unittest.main()
