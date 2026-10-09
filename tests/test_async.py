from contextvars import ContextVar
from importlib import import_module
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import torch

from pipeworks.models import PipelineContext, Step


from pipeworks.embedded.async_step import Async


class FunctionStep(Step):
    def __init__(self, function):
        self.function = function
        self.starts = 0
        self.config = None

    def configure(self, config):
        self.config = config

    def process(self, inputs):
        self.starts += 1
        for index, item in enumerate(inputs):
            yield self.function(item, index)


class AsyncTests(unittest.TestCase):
    def test_public_import_and_validation(self):
        from pipeworks.embedded import Async as exported
        self.assertIs(exported, Async)
        self.assertEqual(Async(FunctionStep(lambda item, _: item)).timeout_ms, 5)
        with self.assertRaises(TypeError):
            Async(object())
        for value in (True, -1, "5", None, float("inf"), float("nan")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                Async(FunctionStep(lambda item, _: item), timeout_ms=value)

    def test_configure_forwards_inner_settings(self):
        inner = FunctionStep(lambda item, _: item)
        step = Async(inner, timeout_ms=25)
        step.configure(SimpleNamespace(step={"inference_interval": 3}))
        self.assertEqual(step.timeout_ms, 25)
        self.assertEqual(vars(inner.config), {"inference_interval": 3})
        step.configure(SimpleNamespace(timeout_ms=10, confidence=0.4))
        self.assertEqual(step.timeout_ms, 10)
        self.assertEqual(vars(inner.config), {"confidence": 0.4})
        with self.assertRaises(ValueError):
            step.configure(SimpleNamespace(step=[]))

    def test_success_preserves_identity_order_and_stream_state(self):
        def process(item, index):
            item.index = index
            del item.removed
            return item

        inner = FunctionStep(process)
        frames = [PipelineContext(removed=True) for _ in range(5)]
        outputs = list(Async(inner, timeout_ms=1000).process(iter(frames)))
        self.assertEqual(inner.starts, 1)
        for index, (output, original) in enumerate(zip(outputs, frames)):
            self.assertIs(output, original)
            self.assertEqual(output.index, index)
            self.assertFalse(hasattr(output, "removed"))

    def test_timeout_busy_pass_through_and_late_mutation_isolation(self):
        entered, release, finished = Event(), Event(), Event()
        self.addCleanup(release.set)
        calls = []

        def process(item, _):
            calls.append(item)
            entered.set()
            release.wait(5)
            item.data["values"].append(99)
            item.tensor.add_(10)
            item.extra = True
            finished.set()
            return item

        frames = [PipelineContext(data={"values": [1]}, tensor=torch.tensor([1])) for _ in range(101)]
        step = Async(FunctionStep(process), timeout_ms=10)
        started = time.monotonic()
        stream = step.process(iter(frames))
        self.assertIs(next(stream), frames[0])
        self.assertLess(time.monotonic() - started, 0.5)
        self.assertTrue(entered.wait(1))
        self.assertEqual(list(stream), frames[1:])
        self.assertEqual(len(calls), 1)
        release.set()
        self.assertTrue(finished.wait(1))
        for frame in frames:
            self.assertEqual(frame.data, {"values": [1]})
            self.assertEqual(frame.tensor.tolist(), [1])
            self.assertFalse(hasattr(frame, "extra"))

    def test_exception_passes_original_and_retries_next_input(self):
        def process(item, _):
            item.data.append(2)
            if item.fail:
                raise RuntimeError("처리 실패")
            return item

        inner = FunctionStep(process)
        frames = [PipelineContext(data=[1], fail=True), PipelineContext(data=[1], fail=False)]
        with self.assertLogs("pipeworks.embedded.async_step", level="ERROR"):
            outputs = list(Async(inner, timeout_ms=1000).process(iter(frames)))
        self.assertIs(outputs[0], frames[0])
        self.assertEqual(frames[0].data, [1])
        self.assertEqual(frames[1].data, [1, 2])
        self.assertEqual(inner.starts, 2)

    def test_new_output_context_is_applied_to_original(self):
        original = PipelineContext(old=True)
        inner = FunctionStep(lambda item, _: PipelineContext(result=7))
        self.assertIs(list(Async(inner, timeout_ms=1000).process(iter([original])))[0], original)
        self.assertEqual(vars(original), {"result": 7})

    def test_success_uses_copied_nested_data_and_preserves_tensor_aliases(self):
        data = [1]
        tensor = torch.tensor([1.0], requires_grad=True) * 2
        original = PipelineContext(data=data, left=tensor, right=tensor)

        def process(item, _):
            self.assertIs(item.left, item.right)
            item.data.append(2)
            item.left.add_(3)
            return item

        list(Async(FunctionStep(process), timeout_ms=1000).process(iter([original])))
        self.assertEqual(data, [1])
        self.assertEqual(tensor.tolist(), [2])
        self.assertEqual(original.data, [1, 2])
        self.assertEqual(original.left.tolist(), [5])
        self.assertIs(original.left, original.right)

    def test_worker_waits_until_the_next_snapshot_is_prepared(self):
        module = import_module("pipeworks.embedded.async_step")
        snapshot = module._snapshot
        preparing, release = Event(), Event()
        self.addCleanup(release.set)
        calls = []

        def process(item, index):
            calls.append(index)
            item.result = index
            return item

        def delayed_snapshot(request):
            if calls:
                preparing.set()
                release.wait(5)
            snapshot(request)

        step = Async(FunctionStep(process), timeout_ms=1000)
        outputs = step.process(iter([PipelineContext(), PipelineContext()]))
        second = []
        with patch.object(module, "_snapshot", side_effect=delayed_snapshot):
            self.assertEqual(next(outputs).result, 0)
            from threading import Thread
            caller = Thread(target=lambda: second.append(next(outputs)))
            caller.start()
            try:
                self.assertTrue(preparing.wait(1))
                self.assertEqual(calls, [0])
                release.set()
                caller.join(2)
                self.assertFalse(caller.is_alive())
                self.assertEqual(second[0].result, 1)
            finally:
                release.set()
                caller.join(2)
                outputs.close()

    def test_request_context_variables_are_propagated(self):
        variable = ContextVar("async_test", default="missing")
        inner = FunctionStep(lambda item, _: PipelineContext(value=variable.get()))

        def frames():
            for value in ("first", "second"):
                token = variable.set(value)
                try:
                    yield PipelineContext()
                finally:
                    variable.reset(token)

        outputs = list(Async(inner, timeout_ms=1000).process(frames()))
        self.assertEqual([item.value for item in outputs], ["first", "second"])

    def test_close_does_not_wait_for_blocked_worker(self):
        release, closed = Event(), Event()
        self.addCleanup(release.set)

        class BlockingStep(Step):
            def process(self, inputs):
                try:
                    for item in inputs:
                        release.wait(5)
                        yield item
                finally:
                    closed.set()

        stream = Async(BlockingStep(), timeout_ms=10).process(iter([PipelineContext()]))
        next(stream)
        started = time.monotonic()
        stream.close()
        self.assertLess(time.monotonic() - started, 0.5)
        release.set()
        self.assertTrue(closed.wait(1))

    def test_reusing_instance_does_not_start_a_second_worker_before_cleanup(self):
        release, closed = Event(), Event()
        self.addCleanup(release.set)
        calls = []

        class BlockingStep(Step):
            def process(self, inputs):
                try:
                    for item in inputs:
                        calls.append(item)
                        release.wait(5)
                        yield item
                finally:
                    closed.set()

        wrapper = Async(BlockingStep(), timeout_ms=10)
        first = wrapper.process(iter([PipelineContext()]))
        next(first)
        first.close()
        original = PipelineContext(value=1)
        self.assertIs(list(wrapper.process(iter([original])))[0], original)
        self.assertEqual(len(calls), 1)
        release.set()
        self.assertTrue(closed.wait(1))

    def test_wrapper_is_serializable_before_use(self):
        import cloudpickle

        wrapper = Async(FunctionStep(lambda item, _: PipelineContext(value=item.value + 1)), timeout_ms=1000)
        restored = cloudpickle.loads(cloudpickle.dumps(wrapper))
        output = list(restored.process(iter([PipelineContext(value=1)])))[0]
        self.assertEqual(output.value, 2)

    def test_uncloneable_input_passes_without_executing(self):
        class Uncloneable:
            def __deepcopy__(self, memo):
                raise TypeError("복사 불가")

        inner = FunctionStep(lambda item, _: item)
        original = PipelineContext(resource=Uncloneable())
        with self.assertLogs("pipeworks.embedded.async_step", level="ERROR"):
            outputs = list(Async(inner, timeout_ms=1000).process(iter([original])))
        self.assertIs(outputs[0], original)
        self.assertEqual(inner.starts, 0)

    def test_contract_violations_pass_original(self):
        class Aggregate(Step):
            def process(self, inputs):
                first = next(inputs)
                next(inputs)
                yield first

        class Source(Step):
            def process(self, inputs):
                yield PipelineContext(invalid=True)

        class Empty(Step):
            def process(self, inputs):
                for _ in inputs:
                    return
                yield

        for inner in (Aggregate(), Source(), Empty()):
            original = PipelineContext(value=1)
            with self.subTest(inner=type(inner).__name__), self.assertLogs("pipeworks.embedded.async_step", level="ERROR"):
                outputs = list(Async(inner, timeout_ms=1000).process(iter([original])))
            self.assertIs(outputs[0], original)
            self.assertEqual(vars(original), {"value": 1})

    def test_zero_timeout_passes_while_worker_runs(self):
        release, entered = Event(), Event()
        self.addCleanup(release.set)

        def process(item, _):
            entered.set()
            release.wait(5)
            item.changed = True
            return item

        original = PipelineContext()
        stream = Async(FunctionStep(process), timeout_ms=0).process(iter([original]))
        self.assertIs(next(stream), original)
        self.assertTrue(entered.wait(1))
        self.assertEqual(vars(original), {})
        stream.close()
        release.set()

    def test_pipeline_applies_async_and_inner_configuration(self):
        from pipeworks import Pipeline

        with TemporaryDirectory() as directory:
            config = Path(directory) / "stream.yml"
            config.write_text("Async:\n  timeout_ms: 100\n  step:\n    confidence: 0.4\n", encoding="utf-8")
            inner = FunctionStep(lambda item, _: item)
            wrapper = Async(inner)
            pipeline = Pipeline("async", config=config).step(wrapper)
            self.assertIs(pipeline.steps[0], wrapper)
            self.assertEqual(wrapper.timeout_ms, 100)
            self.assertEqual(vars(inner.config), {"confidence": 0.4})

    def test_worker_prints_use_the_callers_output_writer(self):
        import sys
        from pipeworks.main import _ThreadOutput

        writes = []
        output = _ThreadOutput(sys.stdout)
        output.current.write = writes.append

        def process(item, _):
            print("Async 작업자 출력")
            return item

        with patch("sys.stdout", output):
            list(Async(FunctionStep(process), timeout_ms=1000).process(iter([PipelineContext()])))
        self.assertIn("Async 작업자 출력", "".join(writes))

    def test_remote_registration_visits_inner_user_step(self):
        import sys
        import pipeworks.main as main

        class Connection:
            def send_bytes(self, value):
                pass

            def recv(self):
                return ("ok", None)

            def close(self):
                pass

        pipeline = SimpleNamespace(steps=[Async(FunctionStep(lambda item, _: item))])
        with patch.object(main, "_connect", return_value=Connection()), \
                patch.object(main.cloudpickle, "register_pickle_by_value") as register, \
                patch.object(main.cloudpickle, "dumps", return_value=b"pipeline"):
            main.run_remote(pipeline)
        register.assert_called_once_with(sys.modules[FunctionStep.__module__])

    @unittest.skipUnless(torch.cuda.is_available(), "CUDA가 필요합니다.")
    def test_gpu_tensor_and_dlpack_frame_are_isolated(self):
        release, done = Event(), Event()
        self.addCleanup(release.set)
        stream = torch.cuda.Stream()
        with torch.cuda.stream(stream):
            tensor = torch.ones((6, 4), dtype=torch.uint8, device="cuda")

        class Frame:
            def __dlpack__(self, stream=None):
                return tensor.__dlpack__(stream=stream)

            def __dlpack_device__(self):
                return tensor.__dlpack_device__()

        def process(item, _):
            release.wait(5)
            with torch.cuda.stream(item.cuda_stream):
                item.frame.add_(1)
                item.model_input.add_(2)
                item.cuda_stream.synchronize()
            done.set()
            return item

        original = PipelineContext(frame=Frame(), model_input=tensor, cuda_stream=stream)
        outputs = Async(FunctionStep(process), timeout_ms=10).process(iter([original]))
        self.assertIs(next(outputs), original)
        outputs.close()
        release.set()
        self.assertTrue(done.wait(2))
        stream.synchronize()
        self.assertTrue(torch.all(tensor == 1).item())
