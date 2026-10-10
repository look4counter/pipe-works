import importlib.util
from contextvars import copy_context
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import torch

from pipeworks.embedded.tensor_rt_inference import TensorRTInference, _EngineSession
from pipeworks.embedded.stream_report import _stats, report_scope
from pipeworks.models import PipelineContext


class FakeContext:
    def __init__(self, api):
        self.api = api
        self.shapes = {}
        self.addresses = {}
        self.allocators = {}
        self.allocator_registrations = []
        self.executions = 0
        self.fail_execute = False

    def set_optimization_profile_async(self, profile_index, stream_handle):
        self.api.profile_selections.append((profile_index, stream_handle))
        self.api.calls.append("profile")
        return self.api.profile_ok

    def set_input_shape(self, name, shape):
        self.api.calls.append("shape")
        self.shapes[name] = tuple(shape)
        return len(shape) == 2 and shape[1] == 2 and 1 <= shape[0] <= 8

    def set_tensor_address(self, name, address):
        self.addresses[name] = address
        return True

    def infer_shapes(self):
        return []

    def get_tensor_shape(self, name):
        return (-1, 2) if self.api.dynamic else self.shapes[self.api.inputs[0]]

    def get_tensor_strides(self, name):
        return (2, 1)

    def set_output_allocator(self, name, allocator):
        self.allocator_registrations.append((name, allocator))
        self.allocators[name] = allocator
        return True

    def execute_async_v3(self, stream_handle):
        self.executions += 1
        self.api.entered.set()
        if self.api.block:
            self.api.release.wait(5)
        if self.fail_execute:
            self.fail_execute = False
            return False
        source = sum(self.api.pointers[self.addresses[name]] for name in self.api.inputs)
        shape = (0, 2) if self.api.empty else tuple(source.shape)
        for index, name in enumerate(self.api.outputs):
            allocator = self.allocators[name]
            dtype = torch.float32 if index == 0 else torch.int32
            size = 0 if self.api.empty else source.numel() * 4
            if self.api.preallocated:
                address = self.addresses[name]
            else:
                address = allocator.reallocate_output_async(name, 0, size, 512, stream_handle)
                self.api.allocations.append((address, 512))
            allocator.notify_shape(name, shape)
            if size:
                allocator.output((2, 1)).copy_((source + index + 1).to(dtype=dtype))
        return True


class FakeTRT:
    TensorIOMode = SimpleNamespace(INPUT="input", OUTPUT="output")
    TensorLocation = SimpleNamespace(DEVICE="device", HOST="host")
    TensorFormat = SimpleNamespace(LINEAR="linear")
    float32 = "float32"
    int32 = "int32"

    class Logger:
        WARNING = 2

        def __init__(self, level):
            pass

    class IOutputAllocator:
        pass

    def __init__(self):
        self.inputs = ["arbitrary_features"]
        self.outputs = ["raw_scores", "raw_indices"]
        self.dynamic = False
        self.empty = False
        self.host = False
        self.vectorized = False
        self.block = False
        self.preallocated = False
        self.entered, self.release = Event(), Event()
        self.pointers = {}
        self.allocations = []
        self.loaded_plugins = []
        self.plugin_ok = True
        self.plugins_initialized = False
        self.payload = None
        self.engine_host_code_allowed = False
        self.contexts = []
        self.profile_selections = []
        self.profile_ok = True
        self.calls = []
        self.format_profiles = []
        self.engine = SimpleNamespace(
            num_optimization_profiles=2,
            num_io_tensors=3,
            get_tensor_name=lambda index: (self.inputs + self.outputs)[index],
            get_tensor_mode=lambda name: "input" if name in self.inputs else "output",
            get_tensor_dtype=lambda name: "int32" if name == self.outputs[1] else "float32",
            get_tensor_shape=lambda name: (-1, 2),
            get_tensor_profile_shape=lambda name, profile_index: ((1, 2), (2, 2), (8, 2)),
            get_tensor_location=lambda name: "host" if self.host else "device",
            get_tensor_format=self.get_tensor_format,
            create_execution_context=self.create_context,
        )

    def get_tensor_format(self, name, profile_index=0):
        self.format_profiles.append(profile_index)
        return "vectorized" if self.vectorized else "linear"

    def create_context(self):
        context = FakeContext(self)
        self.contexts.append(context)
        return context

    def init_libnvinfer_plugins(self, logger, namespace):
        self.plugins_initialized = True
        return True

    def Runtime(self, logger):
        api = self

        class Runtime:
            engine_host_code_allowed = False

            def get_plugin_registry(self):
                return SimpleNamespace(load_library=self.load_library)

            def load_library(self, path):
                api.loaded_plugins.append(path)
                return object() if api.plugin_ok else None

            def deserialize_cuda_engine(self, payload):
                api.payload = payload
                api.engine_host_code_allowed = self.engine_host_code_allowed
                return api.engine

        return Runtime()


class SettingsTests(unittest.TestCase):
    def test_profile_and_plugins_settings(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "model.engine"
            step = TensorRTInference(path)
            self.assertEqual(step._model_settings(), ())
            self.assertEqual(step.profile_index, 0)
            step.configure(SimpleNamespace(profile_index=1))
            self.assertEqual(step.profile_index, 1)
            for value in (-1, True, 1.5, "1", None):
                with self.subTest(value=value):
                    with self.assertRaisesRegex(ValueError, "profile_index"):
                        step.configure(SimpleNamespace(gpu_id=2, inference_interval_frame=3, profile_index=value))
                    self.assertEqual((step.gpu_id, step.inference_interval_frame, step.profile_index), (0, 1, 1))
            path.with_suffix(".yml").write_text("plugins: [custom.dll]", encoding="utf-8")
            self.assertEqual(step._model_settings(), (path.parent / "custom.dll",))
            for text in ("profile_index: 1", "timeout: 20", "plugins: [null]", "plugins: ['']"):
                with self.subTest(text=text):
                    path.with_suffix(".yml").write_text(text, encoding="utf-8")
                    with self.assertRaises(ValueError):
                        step._model_settings()

    def test_interval_default_and_configuration_update(self):
        step = TensorRTInference(Path("model.engine"))
        self.assertEqual(step.inference_interval_frame, 1)
        self.assertFalse(hasattr(step, "inference_interval"))
        step.configure(SimpleNamespace(inference_interval_frame=3))
        self.assertEqual(step.inference_interval_frame, 3)
        step.configure(SimpleNamespace())
        self.assertEqual(step.inference_interval_frame, 1)

    def test_invalid_interval_preserves_settings(self):
        step = TensorRTInference(Path("model.engine"))
        step.configure(SimpleNamespace(gpu_id=1, inference_interval_frame=3))
        for value in (0, -1, True, 1.5, "3", None):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "inference_interval_frame"):
                    step.configure(SimpleNamespace(gpu_id=0, inference_interval_frame=value))
                self.assertEqual((step.gpu_id, step.inference_interval_frame), (1, 3))

    def test_old_interval_key_is_rejected_without_changing_settings(self):
        step = TensorRTInference(Path("model.engine"))
        step.configure(SimpleNamespace(gpu_id=1, inference_interval_frame=3))
        for config in ({"inference_interval": 2},
                       {"inference_interval": 2, "inference_interval_frame": 4}):
            with self.subTest(config=config):
                with self.assertRaisesRegex(ValueError, "inference_interval_frame"):
                    step.configure(SimpleNamespace(gpu_id=0, **config))
                self.assertEqual((step.gpu_id, step.inference_interval_frame), (1, 3))

    def test_batch_flag_validation(self):
        self.assertFalse(TensorRTInference(Path("model.plan")).batch)
        self.assertTrue(TensorRTInference(Path("model.plan"), batch=True).batch)
        for value in (0, 1, None, "true"):
            with self.assertRaises(ValueError):
                TensorRTInference(Path("model.plan"), batch=value)
    def test_settings_and_public_export(self):
        from pipeworks.embedded import TensorRTInference as exported
        self.assertIs(exported, TensorRTInference)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "model.engine"
            step = TensorRTInference(path)
            self.assertEqual(step._model_settings(), ())
            path.with_suffix(".yml").write_text("timeout_ms: 25\nplugins: [custom.dll]\nmax_batch_size: 10", encoding="utf-8")
            plugins = step._model_settings()
            self.assertEqual(plugins, (Path(directory) / "custom.dll",))
            step.configure(SimpleNamespace(gpu_id=1, inference_interval_frame=3))
            self.assertEqual((step.gpu_id, step.inference_interval_frame), (1, 3))

    def test_invalid_settings_are_rejected(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "model.engine"
            for value in ("true", "-1", ".inf", ".nan", '"5"', "null"):
                path.with_suffix(".yml").write_text(f"timeout_ms: {value}", encoding="utf-8")
                self.assertEqual(TensorRTInference(path)._model_settings(), ())
            for content in ("[]", "timeout_ms: [", "plugins: wrong", "plugins: [3]"):
                path.with_suffix(".yml").write_text(content, encoding="utf-8")
                with self.assertRaises(ValueError):
                    TensorRTInference(path)._model_settings()
        for config in (SimpleNamespace(gpu_id=True), SimpleNamespace(gpu_id=-1),
                       SimpleNamespace(inference_interval_frame=0), SimpleNamespace(inference_interval_frame=True)):
            with self.assertRaises(ValueError):
                TensorRTInference(Path("model.engine")).configure(config)


class ProfileSelectionTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "model.engine"
        self.path.write_bytes(b"engine")
        self.api = FakeTRT()
        self.patcher = patch.dict("sys.modules", {"tensorrt": self.api})
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_selects_profile_once_before_binding_on_execution_stream(self):
        session = _EngineSession(self.path, profile_index=1)
        stream = SimpleNamespace(cuda_stream=123, synchronize=Mock())
        with patch.object(session, "_bind", side_effect=lambda *args: self.api.calls.append("bind")), \
                patch.object(session.context, "execute_async_v3", return_value=True):
            session.infer({}, stream, copy_context())
            session.infer({}, stream, copy_context())
        self.assertEqual(self.api.profile_selections, [(1, 123)])
        self.assertEqual(self.api.calls, ["profile", "bind", "bind"])
        self.assertEqual(self.api.format_profiles, [1, 1, 1])

    def test_rejects_out_of_range_profile_and_selection_failure(self):
        with self.assertRaisesRegex(ValueError, "profile_index.*2"):
            _EngineSession(self.path, profile_index=2)
        session = _EngineSession(self.path, profile_index=1)
        self.api.profile_ok = False
        with patch.object(session, "_bind") as bind:
            with self.assertRaisesRegex(RuntimeError, "1"):
                session.infer({}, SimpleNamespace(cuda_stream=123), copy_context())
            bind.assert_not_called()


@unittest.skipUnless(torch.cuda.is_available(), "CUDA가 필요합니다.")
class TensorRTInferenceTests(unittest.TestCase):
    def test_batch_submits_inputs_events_interval_and_statistics(self):
        step = TensorRTInference(self.path, batch=True)
        step.configure(SimpleNamespace(inference_interval_frame=3))
        items = [self.item() for _ in range(7)]
        calls = []

        def infer(path, tensors, gpu_id, *, profile_index, ready_event, on_inference_complete):
            self.assertEqual(profile_index, step.profile_index)
            ready_event.synchronize()
            calls.append(tensors)
            on_inference_complete(.01)
            return {"output": tensors + 1}

        with patch("pipeworks.local_tensor_rt.infer", side_effect=infer), report_scope():
            stats = _stats()
            outputs = list(step.process(iter(items)))
        self.assertEqual(outputs, items)
        self.assertEqual([i.model_output is not None for i in items], [True, False, False, True, False, False, True])
        self.assertEqual(stats.completed_inferences, 3)
        self.assertEqual(len(calls), 3)
        for tensor, item in zip(calls, items[::3]):
            self.assertIs(tensor, item.model_input)
        with patch("pipeworks.local_tensor_rt.infer", side_effect=RuntimeError("batch failed")):
            with self.assertRaisesRegex(RuntimeError, "batch failed"):
                list(step.process(iter([self.item()])))
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "model.engine"
        self.path.write_bytes(b"serialized-engine")
        self.path.with_suffix(".yml").write_text("timeout_ms: 2000", encoding="utf-8")
        self.api = FakeTRT()
        module = patch.dict("sys.modules", {"tensorrt": self.api})
        module.start()
        self.addCleanup(module.stop)
        original_ptr = torch.Tensor.data_ptr

        def data_ptr(tensor):
            address = original_ptr(tensor)
            self.api.pointers[address] = tensor
            return address

        pointer_patch = patch.object(torch.Tensor, "data_ptr", data_ptr)
        pointer_patch.start()
        self.addCleanup(pointer_patch.stop)
        self.step = TensorRTInference(self.path)
        self.addCleanup(self.stop_worker)

    def stop_worker(self):
        self.api.release.set()

    def item(self, value=1):
        stream = torch.cuda.Stream()
        with torch.cuda.stream(stream):
            tensor = torch.full((2, 2), value, dtype=torch.float32, device="cuda")
        return PipelineContext(model_input=tensor, model_output=object(), cuda_stream=stream, frame=object())

    def test_repeated_inference_registers_one_allocator_per_binding(self):
        items = [self.item(value) for value in range(1, 6)]
        results = list(self.step.process(iter(items)))
        context = self.api.contexts[0]
        self.assertEqual(len(context.allocator_registrations), len(self.api.outputs))
        for value, item in enumerate(results, 1):
            self.assertTrue(torch.equal(item.model_output["raw_scores"],
                                        torch.full((2, 2), value + 1, device="cuda")))

    def test_single_input_names_gpu_values_and_no_pre_or_post_processing(self):
        item = self.item(3)
        source, frame = item.model_input, item.frame
        with patch.object(torch.Tensor, "cpu", side_effect=AssertionError("CPU 복사 금지")), patch.object(
            torch.Tensor, "numpy", side_effect=AssertionError("NumPy 변환 금지")
        ):
            self.assertEqual(list(self.step.process(iter((item,)))), [item])
        self.assertIs(item.model_input, source)
        self.assertIs(item.frame, frame)
        self.assertEqual(set(item.model_output), set(self.api.outputs))
        torch.testing.assert_close(item.model_output["raw_scores"], source + 1)
        torch.testing.assert_close(item.model_output["raw_indices"], (source + 2).to(torch.int32))
        self.assertTrue(all(tensor.is_cuda for tensor in item.model_output.values()))
        self.assertTrue(self.api.plugins_initialized)
        self.assertTrue(self.api.engine_host_code_allowed)
        self.assertTrue(all(pointer % alignment == 0 for pointer, alignment in self.api.allocations))

    def test_fixed_output_uses_preallocated_buffer_without_callback(self):
        self.api.preallocated = True
        item = self.item(5)
        list(self.step.process(iter((item,))))
        torch.testing.assert_close(item.model_output["raw_scores"], item.model_input + 1)
        self.assertEqual(self.api.allocations, [])

    def test_noncontiguous_input_is_copied_without_changing_values(self):
        item = self.item()
        item.model_input = torch.arange(4, dtype=torch.float32, device="cuda").reshape(2, 2).t()
        item.cuda_stream = torch.cuda.current_stream()
        self.assertFalse(item.model_input.is_contiguous())
        list(self.step.process(iter((item,))))
        torch.testing.assert_close(item.model_output["raw_scores"], item.model_input + 1)
        self.assertFalse(item.model_input.is_contiguous())

    def test_async_owns_timeout_during_engine_initialization(self):
        from pipeworks.embedded import CudaAsync
        entered, release = Event(), Event()
        self.addCleanup(release.set)

        def load(*arguments):
            entered.set()
            release.wait(5)
            return _EngineSession(*arguments)

        wrapper = CudaAsync(self.step, timeout_ms=20)
        with patch("pipeworks.embedded.tensor_rt_inference._EngineSession", side_effect=load):
            items = [self.item(), self.item()]
            outputs = wrapper.process(iter(items))
            try:
                self.assertIs(next(outputs), items[1])
                self.assertTrue(entered.wait(2))
                with self.assertRaises(StopIteration):
                    next(outputs)
            finally:
                outputs.close()
                release.set()
                self.assertTrue(wrapper._session_lock.acquire(timeout=3))
                wrapper._session_lock.release()

    def test_multiple_inputs_dynamic_outputs_and_empty_outputs(self):
        self.api.inputs.append("another_tensor")
        self.api.engine.num_io_tensors = 4
        self.api.dynamic = True
        item = self.item(2)
        item.model_input = {name: item.model_input for name in self.api.inputs}
        self.assertEqual(list(self.step.process(iter((item,)))), [item])
        torch.testing.assert_close(item.model_output["raw_scores"], item.model_input[self.api.inputs[0]] * 2 + 1)
        self.api.empty = True
        second = self.item()
        second.model_input = {name: second.model_input for name in self.api.inputs}
        list(self.step.process(iter((second,))))
        self.assertEqual(tuple(second.model_output["raw_scores"].shape), (0, 2))

    def test_plugin_libraries_and_metadata_header(self):
        plugin = Path(self.directory.name) / "custom.dll"
        plugin.write_bytes(b"plugin")
        metadata = b'{"description": "metadata"}'
        self.path.write_bytes(len(metadata).to_bytes(4, "little") + metadata + b"raw-engine")
        session = _EngineSession(self.path, (plugin,))
        self.assertEqual(self.api.payload, b"raw-engine")
        self.assertEqual(self.api.loaded_plugins, [str(plugin)])
        self.assertTrue(session)
        self.api.plugin_ok = False
        with self.assertRaises(RuntimeError):
            _EngineSession(self.path, (plugin,))
        with self.assertRaises(FileNotFoundError):
            _EngineSession(self.path, (plugin.with_name("missing.dll"),))

    def test_model_yaml_passes_profile_and_plugins_to_session(self):
        plugin = Path(self.directory.name) / "custom.dll"
        plugin.write_bytes(b"plugin")
        self.path.with_suffix(".yml").write_text("plugins: [custom.dll]", encoding="utf-8")
        self.step.configure(SimpleNamespace(profile_index=1))
        list(self.step.process(iter([self.item()])))
        self.assertEqual(self.api.loaded_plugins, [str(plugin)])
        self.assertEqual(self.api.profile_selections[0][0], 1)
        self.assertEqual(self.api.calls[:2], ["profile", "shape"])

    def test_profile_change_recreates_session_for_next_input(self):
        first, second = self.item(), self.item()
        def inputs():
            yield first
            self.step.configure(SimpleNamespace(profile_index=1))
            yield second
        self.assertEqual(list(self.step.process(inputs())), [first, second])
        self.assertEqual([index for index, _ in self.api.profile_selections], [0, 1])
        self.assertEqual(len(self.api.contexts), 2)

    def test_invalid_inputs_formats_and_execution_failures_recover(self):
        for invalid in ("cpu", "dtype", "names", "shape", "host", "format", "execution"):
            with self.subTest(invalid=invalid):
                self.stop_worker()
                self.api.contexts.clear()
                self.step = TensorRTInference(self.path)
                first, second = self.item(), self.item()
                if invalid == "cpu":
                    first.model_input = torch.ones((2, 2))
                elif invalid == "dtype":
                    first.model_input = first.model_input.half()
                elif invalid == "names":
                    first.model_input = {"wrong_name": first.model_input}
                elif invalid == "shape":
                    first.model_input = torch.ones((9, 2), device="cuda")
                elif invalid == "host":
                    self.api.host = True
                elif invalid == "format":
                    self.api.vectorized = True
                else:
                    original_create = self.api.engine.create_execution_context

                    def create():
                        context = original_create()
                        context.fail_execute = True
                        return context

                    self.api.engine.create_execution_context = create
                with self.assertRaises((ValueError, RuntimeError)):
                    list(self.step.process(iter((first,))))
                self.api.host = self.api.vectorized = False
                if invalid == "execution":
                    self.api.engine.create_execution_context = original_create
                list(self.step.process(iter((second,))))
                self.assertIsNotNone(second.model_output)

    def test_contiguous_input_is_not_cloned_and_runs_on_caller_thread(self):
        from threading import get_ident
        caller = get_ident()
        original = _EngineSession.infer
        observed = []
        item = self.item()

        def infer(session, tensors, stream, context):
            observed.append((get_ident(), tensors.data_ptr()))
            return original(session, tensors, stream, context)

        with patch.object(_EngineSession, "infer", infer), patch.object(torch.Tensor, "clone", side_effect=AssertionError("unexpected clone")):
            list(self.step.process(iter((item,))))
        self.assertEqual(observed, [(caller, item.model_input.data_ptr())])

    def test_interval_and_request_scope_statistics(self):
        self.step.inference_interval_frame = 3
        items = [self.item() for _ in range(7)]
        with report_scope():
            stats = _stats()
            outputs = list(self.step.process(iter(items)))
        self.assertEqual(outputs, items)
        self.assertEqual(stats.completed_inferences, 3)
        self.assertEqual([item.model_output is not None for item in items], [True, False, False, True, False, False, True])


@unittest.skipUnless(importlib.util.find_spec("tensorrt") and torch.cuda.is_available(), "TensorRT와 CUDA가 필요합니다.")
class RealTensorRTTests(unittest.TestCase):
    def test_model_yaml_selects_second_profile_in_both_modes(self):
        import tensorrt as trt
        with TemporaryDirectory() as directory:
            logger = trt.Logger(trt.Logger.WARNING)
            builder = trt.Builder(logger)
            network = builder.create_network(0)
            value = network.add_input("features", trt.float32, (-1, -1))
            output = network.add_elementwise(value, value, trt.ElementWiseOperation.SUM).get_output(0)
            output.name = "result"
            network.mark_output(output)
            config = builder.create_builder_config()
            for width in (2, 4):
                profile = builder.create_optimization_profile()
                profile.set_shape("features", (1, width), (2, width), (4, width))
                config.add_optimization_profile(profile)
            serialized = builder.build_serialized_network(network, config)
            self.assertIsNotNone(serialized)
            path = Path(directory) / "profiles.engine"
            path.write_bytes(bytes(serialized))
            path.with_suffix(".yml").write_text("plugins: []", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "프로파일 0"):
                item = PipelineContext(model_input=torch.ones((1, 4), device="cuda"))
                list(TensorRTInference(path).process(iter([item])))
            for batch in (False, True):
                with self.subTest(batch=batch):
                    source = torch.ones((1, 4), device="cuda")
                    item = PipelineContext(model_input=source)
                    step = TensorRTInference(path, batch=batch)
                    step.configure(SimpleNamespace(profile_index=1))
                    list(step.process(iter([item])))
                    torch.testing.assert_close(item.model_output["result"], source * 2)

    def test_real_engine_raw_gpu_output(self):
        import tensorrt as trt
        with TemporaryDirectory() as directory:
            logger = trt.Logger(trt.Logger.WARNING)
            builder = trt.Builder(logger)
            network = builder.create_network(0)
            value = network.add_input("unfixed_input_name", trt.float32, (2, 2))
            layer = network.add_elementwise(value, value, trt.ElementWiseOperation.SUM)
            layer.get_output(0).name = "unfixed_output_name"
            network.mark_output(layer.get_output(0))
            serialized = builder.build_serialized_network(network, builder.create_builder_config())
            self.assertIsNotNone(serialized)
            path = Path(directory) / "model.engine"
            path.write_bytes(bytes(serialized))
            path.with_suffix(".yml").write_text("timeout_ms: 10000", encoding="utf-8")
            step = TensorRTInference(path)
            item = PipelineContext(model_input=torch.ones((2, 2), device="cuda"))
            list(step.process(iter((item,))))
            self.assertIsNotNone(item.model_output)
            torch.testing.assert_close(item.model_output["unfixed_output_name"], item.model_input * 2)



if __name__ == "__main__":
    unittest.main()
