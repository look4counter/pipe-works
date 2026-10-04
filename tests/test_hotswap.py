import sys
import tempfile
import types
import unittest
import uuid
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pipeworks.hotswap import Hotswap
from pipeworks.models import PipelineContext, Step
from pipeworks.pipeline import Pipeline
from pipeworks.embedded.nvidia_decode import NvidiaDecode
from pipeworks.embedded.rtsp_source import RTSPSource
from pipeworks.embedded.rtsp_publish import RTSPPublish
from pipeworks.embedded.sink import Sink as BackgroundSink


def load_step(path: Path, class_name: str, *args):
    module_name = f"hotswap_test_{id(path)}"
    module = types.ModuleType(module_name)
    module.__file__ = str(path)
    module.__package__ = ""
    sys.modules[module_name] = module
    exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), module.__dict__)
    return getattr(module, class_name)(*args)


def metadata_code(first_offset: int, second_offset: int) -> str:
    return f'''
from pipeworks.models import PipelineContext, Step

class Metadata(Step):
    def process(self, inputs):
        for context in inputs:
            yield PipelineContext(value=context.value + {first_offset})
            yield PipelineContext(value=context.value + {second_offset})
'''


class Accumulator(Step):
    def process(self, inputs):
        total = 0
        for context in inputs:
            total += context.value
            yield PipelineContext(value=total)


class NamedAccumulator(Step):
    def __init__(self, label):
        self.label = label
        self.total = 0

    def process(self, inputs):
        for context in inputs:
            self.total += context.value
            yield PipelineContext(value=self.total)


class HotswapTests(unittest.TestCase):
    def test_source_configure_keeps_active_generator_open(self):
        closed = []

        class Source(Step):
            def configure(self, config):
                self.value = config.value

            def process(self, inputs):
                try:
                    yield PipelineContext(value=self.value)
                    yield PipelineContext(value=self.value)
                finally:
                    closed.append(True)

        original = Source()
        wrapper = Hotswap(original, source=True, watch_code=False, check_interval=0)
        wrapper.configure(SimpleNamespace(value=10))
        active_config = SimpleNamespace(value=10)
        wrapper._config_provider = lambda: active_config
        iterator = wrapper.process(iter(()))
        self.assertEqual(next(iterator).value, 10)
        active_config = SimpleNamespace(value=20)
        self.assertEqual(next(iterator).value, 20)
        self.assertIs(wrapper.wrapped_step, original)
        self.assertEqual(closed, [])
        iterator.close()
        self.assertEqual(closed, [True])

    def test_code_and_config_change_apply_together(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "configured.py"

            def code(extra):
                return (
                    "from pipeworks.models import PipelineContext, Step\n"
                    "class Configured(Step):\n"
                    "    def configure(self, config):\n"
                    "        self.offset = config.offset\n"
                    "    def process(self, inputs):\n"
                    "        for item in inputs:\n"
                    f"            yield PipelineContext(value=item.value + self.offset + {extra})\n"
                )

            path.write_text(code(0), encoding="utf-8")
            wrapper = Hotswap(load_step(path, "Configured"), check_interval=0)
            wrapper.configure(SimpleNamespace(offset=10))
            active_config = SimpleNamespace(offset=10)
            wrapper._config_provider = lambda: active_config
            iterator = wrapper.process(iter([PipelineContext(value=1), PipelineContext(value=2)]))
            self.assertEqual(next(iterator).value, 11)
            path.write_text(code(100), encoding="utf-8")
            active_config = SimpleNamespace(offset=20)
            self.assertEqual(next(iterator).value, 122)
            iterator.close()

    def test_reload_resolves_neighbor_module_without_leaking_import_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            helper_name = f"hotswap_neighbor_{uuid.uuid4().hex}"
            (root / f"{helper_name}.py").write_text("OFFSET = 100\n", encoding="utf-8")
            path = root / "user_step.py"

            def code(offset):
                return (
                    f"from {helper_name} import OFFSET\n"
                    "from pipeworks.models import Step, PipelineContext\n"
                    "class UserStep(Step):\n"
                    "    def process(self, inputs):\n"
                    "        for item in inputs:\n"
                    f"            yield PipelineContext(value=item.value + OFFSET + {offset})\n"
                )

            path.write_text(code(0), encoding="utf-8")
            sys.path.insert(0, str(root))
            try:
                step = load_step(path, "UserStep")
            finally:
                sys.path.remove(str(root))
            sys.modules.pop(helper_name, None)
            wrapper = Hotswap(step, check_interval=0)
            iterator = wrapper.process(iter([PipelineContext(value=1), PipelineContext(value=2)]))
            self.assertEqual(next(iterator).value, 101)
            path.write_text(code(1000), encoding="utf-8")
            before = sys.path.copy()
            try:
                self.assertEqual(next(iterator).value, 1102)
                self.assertEqual(sys.path, before)
            finally:
                iterator.close()
                sys.modules.pop(helper_name, None)

    def test_reload_resolves_package_root_outside_runtime_import_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package_name = f"user_package_{uuid.uuid4().hex}"
            package_dir = root / package_name
            package_dir.mkdir()
            (package_dir / "__init__.py").write_text("", encoding="utf-8")
            (package_dir / "helper.py").write_text("OFFSET = 100\n", encoding="utf-8")
            path = package_dir / "worker.py"

            def code(offset):
                return (
                    f"from {package_name}.helper import OFFSET\n"
                    "from pipeworks.models import Step, PipelineContext\n"
                    "class UserStep(Step):\n"
                    "    def process(self, inputs):\n"
                    "        for item in inputs:\n"
                    f"            yield PipelineContext(value=item.value + OFFSET + {offset})\n"
                )

            path.write_text(code(0), encoding="utf-8")
            module_name = f"{package_name}.worker"
            module = types.ModuleType(module_name)
            module.__file__ = str(path)
            module.__package__ = package_name
            sys.modules[module_name] = module
            sys.path.insert(0, str(root))
            try:
                exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), module.__dict__)
                wrapper = Hotswap(module.UserStep(), check_interval=0)
            finally:
                sys.path.remove(str(root))
                sys.modules.pop(f"{package_name}.helper", None)
            iterator = wrapper.process(iter([PipelineContext(value=1), PipelineContext(value=2)]))
            try:
                self.assertEqual(next(iterator).value, 101)
                path.write_text(code(1000), encoding="utf-8")
                before = sys.path.copy()
                self.assertEqual(next(iterator).value, 1102)
                self.assertEqual(sys.path, before)
            finally:
                iterator.close()
                sys.modules.pop(module_name, None)
                sys.modules.pop(f"{package_name}.helper", None)
                sys.modules.pop(package_name, None)

    def test_user_step_error_passes_original_frame_and_continues(self):
        class Fragile(Step):
            def process(self, inputs):
                for item in inputs:
                    if item.value == 2:
                        raise ValueError("bad frame")
                    yield PipelineContext(value=item.value * 10)

        frames = [PipelineContext(value=value) for value in (1, 2, 3)]
        with self.assertLogs("pipeworks.hotswap", level="ERROR"):
            outputs = list(Hotswap(Fragile()).process(iter(frames)))

        self.assertEqual([item.value for item in outputs], [10, 2, 30])
        self.assertIs(outputs[1], frames[1])

    def test_user_step_error_restores_original_context_fields(self):
        class Mutating(Step):
            def process(self, inputs):
                for item in inputs:
                    item.frame = "changed"
                    item.extra = "temporary"
                    raise RuntimeError("failed after mutation")
                    yield item

        original = PipelineContext(frame=object(), value=4)
        original_frame = original.frame
        with self.assertLogs("pipeworks.hotswap", level="ERROR"):
            outputs = list(Hotswap(Mutating()).process(iter((original,))))
        self.assertEqual(outputs, [original])
        self.assertIs(outputs[0].frame, original_frame)
        self.assertFalse(hasattr(outputs[0], "extra"))

    def test_user_step_close_error_does_not_stop_pipeline(self):
        class FailsOnClose(Step):
            def process(self, inputs):
                class Output:
                    def __iter__(self):
                        return self

                    def __next__(self):
                        return next(inputs)

                    def close(self):
                        raise RuntimeError("close failed")

                return Output()

        original = PipelineContext(value=1)
        iterator = Hotswap(FailsOnClose()).process(iter((original,)))
        self.assertEqual(next(iterator).value, 1)
        with self.assertLogs("pipeworks.hotswap", level="ERROR"):
            self.assertEqual(list(iterator), [])

    def test_user_step_error_passes_all_unreturned_inputs(self):
        class Buffered(Step):
            def process(self, inputs):
                for first in inputs:
                    second = next(inputs)
                    raise RuntimeError("buffer failed")
                    yield first, second

        frames = [PipelineContext(value=value) for value in (1, 2)]
        with self.assertLogs("pipeworks.hotswap", level="ERROR"):
            outputs = list(Hotswap(Buffered()).process(iter(frames)))
        self.assertEqual(outputs, frames)
        self.assertIs(outputs[0], frames[0])
        self.assertIs(outputs[1], frames[1])

    def test_error_before_input_passes_each_frame(self):
        class Broken(Step):
            def process(self, inputs):
                raise RuntimeError("cannot start")

        frames = [PipelineContext(value=value) for value in (1, 2)]
        with self.assertLogs("pipeworks.hotswap", level="ERROR"):
            outputs = list(Hotswap(Broken()).process(iter(frames)))
        self.assertEqual(outputs, frames)

    def test_upstream_error_is_not_swallowed(self):
        class Passthrough(Step):
            def process(self, inputs):
                yield from inputs

        def source():
            yield PipelineContext(value=1)
            raise RuntimeError("upstream failed")

        iterator = Hotswap(Passthrough()).process(source())
        self.assertEqual(next(iterator).value, 1)
        with self.assertRaisesRegex(RuntimeError, "upstream failed"):
            next(iterator)

    def test_user_source_error_retries(self):
        class FragileSource(Step):
            def __init__(self, attempts):
                self.attempts = attempts

            def process(self, inputs):
                self.attempts.append(1)
                if len(self.attempts) == 1:
                    raise RuntimeError("temporary source failure")
                yield PipelineContext(value=7)

        attempts = []
        with self.assertLogs("pipeworks.hotswap", level="ERROR"):
            outputs = list(Hotswap(FragileSource(attempts), source=True).process(iter(())))
        self.assertEqual([item.value for item in outputs], [7])
        self.assertEqual(len(attempts), 2)

    def test_pipeline_continues_after_user_step_error(self):
        frames = [PipelineContext(value=value, frame=object()) for value in (1, 2, 3)]
        seen = []

        class Source(Step):
            def process(self, inputs):
                yield from frames

        class Fragile(Step):
            def process(self, inputs):
                for item in inputs:
                    if item.value == 2:
                        raise RuntimeError("bad frame")
                    yield item

        class Collect(Step):
            def process(self, inputs):
                for item in inputs:
                    seen.append(item)
                yield from ()

        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.yaml"
            config.write_text("{}", encoding="utf-8")
            pipeline = Pipeline("test", config=config).step(Source()).step(Fragile()).step(Collect())
            with self.assertLogs("pipeworks.hotswap", level="ERROR"):
                pipeline._run_local()

        self.assertEqual(seen, frames)
        self.assertTrue(all(output is original for output, original in zip(seen, frames)))

    def test_pipeline_excludes_embedded_steps_from_automatic_hotswap(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.yaml"
            config.write_text("RTSPSource:\n  reconnect: false\n", encoding="utf-8")
            source = RTSPSource("rtsp://example.invalid/stream")
            pipeline = Pipeline("test", config=config).step(source).step(Accumulator())

            self.assertIs(pipeline.steps[0], source)
            self.assertFalse(source.reconnect)
            self.assertIsInstance(pipeline.steps[1], Hotswap)

    def test_sink_excludes_embedded_child_and_keeps_user_step_hotswap(self):
        publish = RTSPPublish("rtsp://example.invalid/output")
        self.assertIs(BackgroundSink(publish).step, publish)
        self.assertIsInstance(BackgroundSink(Accumulator()).step, Hotswap)

        explicit = Hotswap(publish)
        self.assertIs(BackgroundSink(explicit).step, explicit)

    def test_pipeline_keeps_explicit_hotswap_for_embedded_step(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.yaml"
            config.write_text("{}", encoding="utf-8")
            wrapped = Hotswap(RTSPSource("rtsp://example.invalid/stream"))
            pipeline = Pipeline("test", config=config).step(wrapped)
            self.assertIs(pipeline.steps[0], wrapped)
            self.assertTrue(wrapped.source)

    def test_change_drains_old_outputs_before_new_code(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "metadata.py"
            path.write_text(metadata_code(0, 100), encoding="utf-8")
            iterator = Hotswap(load_step(path, "Metadata"), check_interval=0).process(
                iter([PipelineContext(value=1), PipelineContext(value=2)])
            )
            self.assertEqual(next(iterator).value, 1)
            path.write_text(metadata_code(1000, 2000), encoding="utf-8")
            self.assertEqual([item.value for item in iterator], [101, 1002, 2002])

    def test_invalid_change_keeps_old_code(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "metadata.py"
            path.write_text(metadata_code(0, 100), encoding="utf-8")
            iterator = Hotswap(load_step(path, "Metadata"), check_interval=0).process(
                iter([PipelineContext(value=1), PipelineContext(value=2)])
            )
            self.assertEqual(next(iterator).value, 1)
            path.write_text("class Metadata(:\n", encoding="utf-8")
            with patch("pipeworks.hotswap.logger.exception"):
                self.assertEqual([item.value for item in iterator], [101, 2, 102])

    def test_code_change_preserves_instance_state(self):
        def counter_code(offset):
            return (
                "from pipeworks.models import Step, PipelineContext\n"
                "class Counter(Step):\n"
                "    def __init__(self):\n"
                "        self.total = 0\n"
                "    def process(self, inputs):\n"
                "        for context in inputs:\n"
                "            self.total += context.value\n"
                f"            yield PipelineContext(value=self.total + {offset})\n"
            )

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "counter.py"
            path.write_text(counter_code(0), encoding="utf-8")
            wrapper = Hotswap(load_step(path, "Counter"), check_interval=0)
            iterator = wrapper.process(iter([PipelineContext(value=1), PipelineContext(value=2)]))
            self.assertEqual(next(iterator).value, 1)
            path.write_text(counter_code(100), encoding="utf-8")
            self.assertEqual(next(iterator).value, 103)
            self.assertEqual(wrapper.wrapped_step.total, 3)

    def test_reloaded_step_receives_wrapper_configuration(self):
        def code(multiplier):
            return (
                "from pipeworks.models import Step, PipelineContext\n"
                "class Configured(Step):\n"
                "    def configure(self, config):\n"
                "        self.offset = config.offset\n"
                "    def process(self, inputs):\n"
                "        for context in inputs:\n"
                f"            yield PipelineContext(value=context.value * {multiplier} + self.offset)\n"
            )

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "configured.py"
            path.write_text(code(1), encoding="utf-8")
            wrapper = Hotswap(load_step(path, "Configured"), check_interval=0)
            wrapper.configure(SimpleNamespace(offset=10))
            iterator = wrapper.process(iter([PipelineContext(value=1), PipelineContext(value=2)]))
            self.assertEqual(next(iterator).value, 11)
            path.write_text(code(2), encoding="utf-8")
            self.assertEqual(next(iterator).value, 14)
            self.assertNotIn("config", vars(wrapper.wrapped_step))

    def test_source_change_restarts_source_generator(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.py"
            path.write_text(
                "from pipeworks.models import Step, PipelineContext\n"
                "class Source(Step):\n"
                "    def process(self, inputs):\n"
                "        try:\n"
                "            while True:\n"
                "                yield PipelineContext(value=1)\n"
                "        finally:\n"
                "            self.closed = True\n",
                encoding="utf-8",
            )
            original = load_step(path, "Source")
            iterator = Hotswap(original, check_interval=0, source=True).process(iter(()))
            self.assertEqual(next(iterator).value, 1)
            path.write_text(
                "from pipeworks.models import Step, PipelineContext\n"
                "class Source(Step):\n"
                "    def process(self, inputs):\n"
                "        while True:\n"
                "            yield PipelineContext(value=2)\n",
                encoding="utf-8",
            )
            self.assertEqual(next(iterator).value, 2)
            self.assertTrue(original.closed)
            iterator.close()

    def test_source_change_restarts_downstream_state(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.py"
            path.write_text(
                "from pipeworks.models import Step, PipelineContext\n"
                "class Source(Step):\n"
                "    def process(self, inputs):\n"
                "        while True:\n"
                "            yield PipelineContext(value=1)\n",
                encoding="utf-8",
            )
            source = Hotswap(load_step(path, "Source"), check_interval=0, source=True)
            downstream = Hotswap(Accumulator(), check_interval=0)
            iterator = downstream.process(source.process(iter(())))
            self.assertEqual(next(iterator).value, 1)
            path.write_text(
                "from pipeworks.models import Step, PipelineContext\n"
                "class Source(Step):\n"
                "    def process(self, inputs):\n"
                "        while True:\n"
                "            yield PipelineContext(value=2)\n",
                encoding="utf-8",
            )
            self.assertEqual(next(iterator).value, 2)
            iterator.close()

    def test_sink_switches_after_input_drain_without_output(self):
        def sink_code(label):
            return (
                "from pipeworks.models import Step\n"
                "class Sink(Step):\n"
                "    def __init__(self, seen):\n"
                "        self.seen = seen\n"
                "    def process(self, inputs):\n"
                "        for context in inputs:\n"
                f"            self.seen.append(('{label}', context.value))\n"
                "        if False:\n"
                "            yield\n"
            )

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sink.py"
            path.write_text(sink_code("old"), encoding="utf-8")
            seen = []
            sink = Hotswap(load_step(path, "Sink", seen), check_interval=0)

            def inputs():
                yield PipelineContext(value=1)
                path.write_text(sink_code("new"), encoding="utf-8")
                yield PipelineContext(value=2)

            self.assertEqual(list(sink.process(inputs())), [])
            self.assertEqual(seen, [("old", 1), ("new", 2)])

    def test_decoder_flushes_delayed_frames_on_input_end(self):
        class Packet:
            pts = 4

            def __bytes__(self):
                return b"compressed"

        class Decoder:
            def GetPixelFormat(self):
                return "NV12"

            def Decode(self, packet):
                return []

            def Flush(self):
                return ["delayed"]

        fake_nvc = types.ModuleType("PyNvVideoCodec")
        fake_nvc.cudaVideoCodec = SimpleNamespace(H264=1, HEVC=2)
        fake_nvc.OutputColorType = SimpleNamespace(NATIVE=1)
        fake_nvc.DisplayDecodeLatencyType = SimpleNamespace(NATIVE=1)
        fake_nvc.PacketData = type("PacketData", (), {})
        fake_nvc.CreateDecoder = lambda **kwargs: Decoder()
        stream = SimpleNamespace(codec=SimpleNamespace(name="h264"))
        decoder = NvidiaDecode()
        decoder.configure(SimpleNamespace(gpu_id=0))
        with patch.dict(sys.modules, {"PyNvVideoCodec": fake_nvc}), patch(
            "pipeworks.embedded.nvidia_decode.torch.cuda.Stream",
            return_value=SimpleNamespace(cuda_stream=1),
        ), patch("pipeworks.embedded.nvidia_decode.torch.cuda.stream", return_value=nullcontext()):
            frames = list(decoder.process(iter([PipelineContext(packet=Packet(), video_stream=stream)])))
        self.assertEqual([frame.frame for frame in frames], ["delayed"])
        self.assertIs(frames[0].video_stream, stream)

    def test_upstream_change_restarts_downstream_without_losing_boundary_item(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "metadata.py"
            path.write_text(metadata_code(0, 100), encoding="utf-8")
            transform = Hotswap(load_step(path, "Metadata"), check_interval=0)
            downstream = Hotswap(Accumulator(), check_interval=0)
            iterator = downstream.process(
                transform.process(iter([PipelineContext(value=1), PipelineContext(value=2)]))
            )
            self.assertEqual(next(iterator).value, 1)
            path.write_text(metadata_code(1000, 2000), encoding="utf-8")
            self.assertEqual([item.value for item in iterator], [102, 1002, 3004])

    def test_upstream_change_recreates_step_with_constructor_argument(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "metadata.py"
            path.write_text(metadata_code(0, 100), encoding="utf-8")
            transform = Hotswap(load_step(path, "Metadata"), check_interval=0)
            downstream = Hotswap(NamedAccumulator("camera"), check_interval=0)
            iterator = downstream.process(
                transform.process(iter([PipelineContext(value=1), PipelineContext(value=2)]))
            )
            self.assertEqual(next(iterator).value, 1)
            path.write_text(metadata_code(1000, 2000), encoding="utf-8")
            self.assertEqual([item.value for item in iterator], [102, 1002, 3004])
            self.assertEqual(downstream.wrapped_step.label, "camera")
            self.assertEqual(downstream.wrapped_step.total, 3004)

    def test_upstream_restart_reapplies_wrapper_configuration(self):
        class ConfiguredAccumulator(Step):
            def configure(self, config):
                self.offset = config.offset

            def process(self, inputs):
                total = 0
                for context in inputs:
                    total += context.value
                    yield PipelineContext(value=total + self.offset)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "metadata.py"
            path.write_text(metadata_code(0, 100), encoding="utf-8")
            transform = Hotswap(load_step(path, "Metadata"), check_interval=0)
            downstream = Hotswap(ConfiguredAccumulator(), check_interval=0)
            downstream.configure(SimpleNamespace(offset=10))
            iterator = downstream.process(
                transform.process(iter([PipelineContext(value=1), PipelineContext(value=2)]))
            )
            self.assertEqual(next(iterator).value, 11)
            path.write_text(metadata_code(1000, 2000), encoding="utf-8")
            self.assertEqual([item.value for item in iterator], [112, 1012, 3014])
            self.assertNotIn("config", vars(downstream.wrapped_step))

    def test_pipeline_configures_original_step_then_wraps_it(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.yaml"
            config.write_text("Accumulator:\n  label: current\n", encoding="utf-8")
            accumulator = Accumulator()
            pipeline = Pipeline("test", config=config).step(accumulator)
            self.assertIsInstance(pipeline.steps[0], Hotswap)
            self.assertIs(pipeline.steps[0].wrapped_step, accumulator)
            self.assertEqual(pipeline.steps[0]._config.label, "current")
            self.assertNotIn("config", vars(accumulator))

    def test_pipeline_run_consumes_wrapped_step_chain(self):
        class Source(Step):
            def process(self, inputs):
                yield PipelineContext(value=1)
                yield PipelineContext(value=2)

        class Sink(Step):
            def __init__(self, seen):
                self.seen = seen

            def process(self, inputs):
                for context in inputs:
                    self.seen.append(context.value)
                yield from ()

        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.yaml"
            config.write_text("{}", encoding="utf-8")
            seen = []
            pipeline = (
                Pipeline("test", config=config)
                .step(Source())
                .step(Accumulator())
                .step(Sink(seen))
            )
            pipeline._run_local()
            self.assertTrue(pipeline.steps[0].source)
            self.assertEqual(seen, [1, 3])

    def test_pipeline_does_not_double_wrap_explicit_hotswap(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.yaml"
            config.write_text("Accumulator:\n  label: explicit\n", encoding="utf-8")
            wrapped = Hotswap(Accumulator(), check_interval=0)
            pipeline = Pipeline("test", config=config).step(wrapped)
            self.assertIs(pipeline.steps[0], wrapped)
            self.assertEqual(wrapped._config.label, "explicit")
            self.assertNotIn("config", vars(wrapped.wrapped_step))


if __name__ == "__main__":
    unittest.main()
