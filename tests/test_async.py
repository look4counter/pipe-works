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


from pipeworks.embedded.cuda_async import CudaAsync


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
    def test_completed_decoder_input_releases_working_context_only(self):
        observed = []
        def process(item, index):
            observed.append(item)
            item.result_value = 7
            return item

        frame = torch.tensor([1])
        lease = object()
        source = PipelineContext(frame=frame, _decode_buffer=lease)
        wrapper = CudaAsync(FunctionStep(process), timeout_ms=1000)
        result = list(wrapper.process(iter([source])))
        self.assertEqual(result, [source])
        self.assertIs(result[0].frame, frame)
        self.assertIs(result[0]._decode_buffer, lease)
        self.assertEqual(result[0].result_value, 7)
        self.assertIsNot(observed[0], source)
        self.assertNotIn("frame", vars(observed[0]))
        self.assertNotIn("_decode_buffer", vars(observed[0]))

    @unittest.skipUnless(torch.cuda.is_available(), "CUDA가 필요합니다.")
    def test_manages_shared_model_stream_and_preserves_video_stream(self):
        from pipeworks.execution import current_model_stream
        producer = torch.cuda.Stream()
        observed = []

        def process(item, index):
            managed = current_model_stream()
            observed.append(managed.cuda_stream)
            self.assertEqual(torch.cuda.current_stream().cuda_stream, managed.cuda_stream)
            self.assertNotEqual(managed.cuda_stream, producer.cuda_stream)
            self.assertIs(item.cuda_stream, producer)
            return item

        wrapper = CudaAsync(FunctionStep(process), FunctionStep(process), timeout_ms=1000)
        list(wrapper.process(iter([PipelineContext(cuda_stream=producer), PipelineContext(cuda_stream=producer)])))
        self.assertEqual(len(set(observed)), 1)
        self.assertEqual(len(observed), 4)
        self.assertIsNone(current_model_stream())

    def test_pipeline_internal_class_settings_change_independently(self):
        from pipeworks import Pipeline
        from pipeworks.pipeline import _LiveConfig, _watch_async_children
        from pipeworks.embedded import YoloDetect

        first = FunctionStep(lambda item, index: PipelineContext(value=inner_value(item)))

        def inner_value(item):
            return item.value + first.config.offset

        class Other(FunctionStep):
            def configure(self, config):
                if config.offset < 0:
                    raise ValueError("invalid offset")
                super().configure(config)

        second = Other(lambda item, index: PipelineContext(value=item.value + second.config.offset))
        nested = CudaAsync(second, timeout_ms=1000)
        wrapper = CudaAsync(first, nested, timeout_ms=1000)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "config.yml"

            def save(a, b):
                path.write_text(f"FunctionStep:\n  offset: {a}\nOther:\n  offset: {b}\nYoloDetect:\n  confidence: 0.4\n", encoding="utf-8")

            save(1, 2)
            pipeline = Pipeline("nested", config=path).step(wrapper)
            self.assertEqual(first.config.offset, 1)
            self.assertEqual(second.config.offset, 2)
            watcher = _LiveConfig(path, vars(pipeline.config), pipeline._config_digest)
            self.addCleanup(watcher.close)
            def notify_config_change():
                watcher.subscription._service.mark_changed(path)
                watcher.last_check = float("-inf")
            _watch_async_children(wrapper, watcher, vars(pipeline.config))
            for step in (wrapper._hot_steps[0], nested._hot_steps[0]):
                step.check_interval = 0
            outputs = wrapper.process(iter([PipelineContext(value=10) for _ in range(4)]))
            try:
                self.assertEqual(next(outputs).value, 13)
                save(3, 2)
                notify_config_change()
                self.assertEqual(next(outputs).value, 15)
                save(4, -1)
                notify_config_change()
                with self.assertLogs("pipeworks.hotswap", level="ERROR"):
                    self.assertEqual(next(outputs).value, 16)
                save(4, 5)
                notify_config_change()
                self.assertEqual(next(outputs).value, 19)
            finally:
                outputs.close()
                self.assertTrue(wrapper._session_lock.acquire(timeout=1))
                wrapper._session_lock.release()

            yolo = YoloDetect(Path("model.pt"))
            embedded = CudaAsync(yolo)
            Pipeline("embedded", config=path).step(embedded)
            self.assertEqual(yolo.confidence, .4)
            _watch_async_children(embedded, watcher, vars(pipeline.config))
            embedded._hot_steps[0].check_interval = 0
            path.write_text("YoloDetect:\n  confidence: 0.6\n", encoding="utf-8")
            notify_config_change()
            embedded._hot_steps[0]._check_for_update(force=True)
            self.assertEqual(yolo.confidence, .6)

    def test_internal_hotswap_reloads_code_and_preserves_settings(self):
        import sys
        from types import ModuleType
        from pipeworks.hotswap import Hotswap

        def code(extra):
            return (
                "from pipeworks.models import Step\n"
                "class Changing(Step):\n"
                "    def configure(self, config):\n"
                "        self.offset = config.offset\n"
                "    def process(self, inputs):\n"
                "        for item in inputs:\n"
                f"            item.value += self.offset + {extra}\n"
                "            yield item\n"
            )

        for multiple in (False, True):
            with self.subTest(multiple=multiple), TemporaryDirectory() as directory:
                path = Path(directory) / "changing.py"
                path.write_text(code(0), encoding="utf-8")
                module = ModuleType("async_changing_test")
                module.__file__ = str(path)
                sys.modules[module.__name__] = module
                self.addCleanup(sys.modules.pop, module.__name__, None)
                exec(compile(code(0), str(path), "exec"), module.__dict__)
                first = module.Changing()
                steps = (first, FunctionStep(lambda item, index: item)) if multiple else (first,)
                wrapper = CudaAsync(*steps, timeout_ms=1000)
                self.assertIsInstance(wrapper._hot_steps[0], Hotswap)
                wrapper._hot_steps[0].check_interval = 0
                wrapper._hot_steps[0].configure(SimpleNamespace(offset=10))
                outputs = wrapper.process(iter([PipelineContext(value=1) for _ in range(4)]))
                try:
                    self.assertEqual(next(outputs).value, 11)
                    path.write_text(code(100), encoding="utf-8")
                    self.assertEqual(next(outputs).value, 111)
                    path.write_text("invalid syntax!", encoding="utf-8")
                    with self.assertLogs("pipeworks.hotswap", level="ERROR"):
                        self.assertEqual(next(outputs).value, 111)
                    path.write_text(code(200), encoding="utf-8")
                    self.assertEqual(next(outputs).value, 211)
                finally:
                    outputs.close()
                    self.assertTrue(wrapper._session_lock.acquire(timeout=1))
                    wrapper._session_lock.release()

    def test_multiple_steps_keep_order_state_and_settings(self):
        first = FunctionStep(lambda item, index: PipelineContext(value=item.value + 1, index=index))
        second = FunctionStep(lambda item, index: PipelineContext(value=item.value * 2, index=item.index, second=index))
        wrapper = CudaAsync(first, second, timeout_ms=1000)
        wrapper._hot_steps[0].configure(SimpleNamespace(offset=1))
        wrapper._hot_steps[1].configure(SimpleNamespace(scale=2))
        frames = [PipelineContext(value=n) for n in range(3)]
        self.assertEqual([item.value for item in wrapper.process(iter(frames))], [2, 4, 6])
        self.assertEqual([item.second for item in frames], [0, 1, 2])
        self.assertEqual((first.starts, second.starts), (1, 1))
        self.assertEqual(vars(first.config), {"offset": 1})
        self.assertIs(wrapper.step, first)
        for config in (SimpleNamespace(steps=[]), SimpleNamespace(steps=[{}, None]), SimpleNamespace(step={}), SimpleNamespace(confidence=.5)):
            with self.assertRaises(ValueError):
                wrapper.configure(config)
        with self.assertRaises(TypeError):
            CudaAsync()
        with self.assertRaises(TypeError):
            CudaAsync(first, object())

    def test_multiple_timeout_skips_remaining_and_ignores_early_release(self):
        from pipeworks.execution import release_input
        entered, unblock, finished = Event(), Event(), Event()
        self.addCleanup(unblock.set)
        def slow(item, index):
            release_input()
            entered.set()
            unblock.wait(5)
            finished.set()
            return item
        final = FunctionStep(lambda item, index: item)
        wrapper = CudaAsync(FunctionStep(slow), final, timeout_ms=100)
        self.assertEqual(list(wrapper.process(iter([PipelineContext(data=[1])]))), [])
        self.assertTrue(entered.is_set())
        unblock.set()
        self.assertTrue(finished.wait(1))
        self.assertTrue(wrapper._session_lock.acquire(timeout=1))
        wrapper._session_lock.release()
        self.assertEqual(final.starts, 0)

    def test_multiple_steps_serialization(self):
        import cloudpickle
        wrapper = CudaAsync(FunctionStep(lambda item, index: item), FunctionStep(lambda item, index: item), timeout_ms=1000)
        restored = cloudpickle.loads(cloudpickle.dumps(wrapper))
        self.assertEqual(len(restored.steps), 2)
        self.assertIs(restored.step, restored.steps[0])
        self.assertEqual(len(list(restored.process(iter([PipelineContext()])))), 1)

    def test_multiple_error_recovers_and_closes_all_stages(self):
        closed = []

        class Tracked(Step):
            def configure(self, config):
                pass

            def process(self, inputs):
                try:
                    for item in inputs:
                        yield item
                finally:
                    closed.append("first")

        def fail(item, index):
            if item.fail:
                raise ValueError("failed")
            item.success = True
            return item

        wrapper = CudaAsync(Tracked(), FunctionStep(fail), timeout_ms=1000)
        with self.assertLogs("pipeworks.embedded.cuda_async", level="ERROR"):
            outputs = list(wrapper.process(iter([PipelineContext(fail=True), PipelineContext(fail=False)])))
        self.assertFalse(hasattr(outputs[0], "success"))
        self.assertTrue(outputs[1].success)
        self.assertTrue(closed)

    def test_release_input_outside_async_is_optional(self):
        from pipeworks.execution import release_input
        self.assertIsNone(release_input())

    def test_release_input_is_scoped_during_process_initialization(self):
        from pipeworks.execution import release_input
        entered, release, finished = Event(), Event(), Event()
        self.addCleanup(release.set)

        class EagerStep(Step):
            def configure(self, config):
                pass

            def process(self, inputs):
                item = next(inputs)
                release_input()
                entered.set()
                release.wait(5)
                finished.set()
                return iter([item])

        with patch.object(torch.Tensor, "clone", side_effect=AssertionError("input clone")) as snapshot:
            outputs = CudaAsync(EagerStep(), timeout_ms=50).process(iter([PipelineContext()]))
            next(outputs)
            self.assertTrue(entered.wait(1))
            snapshot.assert_not_called()
            outputs.close()
            release.set()
            self.assertTrue(finished.wait(1))

    def test_release_input_passes_only_when_event_is_complete(self):
        from pipeworks.execution import release_input
        for ready in (None, SimpleNamespace(query=lambda: True), SimpleNamespace(query=lambda: False)):
            with self.subTest(ready=ready):
                unblock = Event()
                self.addCleanup(unblock.set)
                def process(item, index):
                    release_input(ready_event=ready)
                    unblock.wait(5)
                    item.late = True
                    return item
                original = PipelineContext(tensor=torch.tensor([1]), data=[1])
                tensor, data = original.tensor, original.data
                wrapper = CudaAsync(FunctionStep(process), timeout_ms=100)
                outputs = list(wrapper.process(iter([original])))
                self.assertEqual(outputs, [original] if ready is None or ready.query() else [])
                self.assertIs(original.tensor, tensor)
                self.assertIs(original.data, data)
                unblock.set()
                self.assertTrue(wrapper._session_lock.acquire(timeout=1))
                wrapper._session_lock.release()
                self.assertFalse(hasattr(original, 'late'))

    def test_release_signal_does_not_leak_to_next_request(self):
        from pipeworks.execution import release_input
        unblock = Event()
        self.addCleanup(unblock.set)
        def process(item, index):
            if index == 0:
                release_input()
            else:
                unblock.wait(5)
            return item
        first, second = PipelineContext(), PipelineContext(tensor=torch.tensor([1]))
        wrapper = CudaAsync(FunctionStep(process), timeout_ms=100)
        self.assertEqual(list(wrapper.process(iter([first, second]))), [first])
        unblock.set()
        self.assertTrue(wrapper._session_lock.acquire(timeout=1))
        wrapper._session_lock.release()

    def test_release_event_query_error_drops_frame(self):
        from pipeworks.execution import release_input
        unblock = Event()
        self.addCleanup(unblock.set)
        class InvalidEvent:
            def query(self):
                raise RuntimeError('query failed')
        def process(item, index):
            release_input(ready_event=InvalidEvent())
            unblock.wait(5)
            return item
        original = PipelineContext(tensor=torch.tensor([1]))
        wrapper = CudaAsync(FunctionStep(process), timeout_ms=100)
        with self.assertLogs('pipeworks.embedded.cuda_async', level='ERROR'):
            self.assertEqual(list(wrapper.process(iter([original]))), [])
        unblock.set()
        self.assertTrue(wrapper._session_lock.acquire(timeout=1))
        wrapper._session_lock.release()

    def test_stale_execution_context_cannot_release_another_request(self):
        from contextvars import copy_context
        from pipeworks.execution import release_input
        unblock = Event()
        self.addCleanup(unblock.set)
        saved = []
        def process(item, index):
            if index == 0:
                saved.append(copy_context())
            else:
                saved[0].run(release_input)
                unblock.wait(5)
            return item
        first, second = PipelineContext(), PipelineContext(tensor=torch.tensor([1]))
        wrapper = CudaAsync(FunctionStep(process), timeout_ms=100)
        self.assertEqual(list(wrapper.process(iter([first, second]))), [first])
        unblock.set()
        self.assertTrue(wrapper._session_lock.acquire(timeout=1))
        wrapper._session_lock.release()

    def test_public_import_and_validation(self):
        from pipeworks.embedded import CudaAsync as exported
        self.assertIs(exported, CudaAsync)
        self.assertEqual(CudaAsync(FunctionStep(lambda item, _: item)).timeout_ms, 5)
        with self.assertRaises(TypeError):
            CudaAsync(object())
        for value in (True, -1, "5", None, float("inf"), float("nan")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                CudaAsync(FunctionStep(lambda item, _: item), timeout_ms=value)

    def test_configure_only_applies_timeout(self):
        inner = FunctionStep(lambda item, _: item)
        wrapper = CudaAsync(inner, timeout_ms=25)
        wrapper.configure(SimpleNamespace(timeout_ms=10))
        self.assertEqual(wrapper.timeout_ms, 10)
        self.assertIsNone(inner.config)
        for config in (SimpleNamespace(step={}), SimpleNamespace(steps=[{}]), SimpleNamespace(confidence=.4)):
            with self.assertRaises(ValueError):
                wrapper.configure(config)

    def test_success_preserves_identity_order_and_stream_state(self):
        def process(item, index):
            item.index = index
            del item.removed
            return item

        inner = FunctionStep(process)
        frames = [PipelineContext(removed=True) for _ in range(5)]
        outputs = list(CudaAsync(inner, timeout_ms=1000).process(iter(frames)))
        self.assertEqual(inner.starts, 1)
        for index, (output, original) in enumerate(zip(outputs, frames)):
            self.assertIs(output, original)
            self.assertEqual(output.index, index)
            self.assertFalse(hasattr(output, "removed"))

    def test_timeout_busy_pass_through_and_late_result_isolation(self):
        entered, unblock, finished = Event(), Event(), Event()
        self.addCleanup(unblock.set)
        calls = []
        def process(item, index):
            calls.append(item)
            entered.set()
            unblock.wait(5)
            item.extra = True
            finished.set()
            return item
        frames = [PipelineContext(data={'values': [1]}, tensor=torch.tensor([1])) for _ in range(101)]
        wrapper = CudaAsync(FunctionStep(process), timeout_ms=100)
        started = time.monotonic()
        with patch.object(torch.Tensor, 'clone', side_effect=AssertionError('input clone')):
            self.assertEqual(list(wrapper.process(iter(frames))), frames[1:])
        self.assertLess(time.monotonic() - started, .5)
        self.assertTrue(entered.is_set())
        self.assertEqual(len(calls), 1)
        self.assertIs(calls[0].tensor, frames[0].tensor)
        unblock.set()
        self.assertTrue(wrapper._session_lock.acquire(timeout=1))
        wrapper._session_lock.release()
        self.assertTrue(finished.is_set())
        for frame in frames:
            self.assertFalse(hasattr(frame, 'extra'))

    def test_exception_passes_original_and_retries_next_input(self):
        def process(item, _):
            item.data = item.data + [2]
            if item.fail:
                raise RuntimeError("처리 실패")
            return item

        inner = FunctionStep(process)
        frames = [PipelineContext(data=[1], fail=True), PipelineContext(data=[1], fail=False)]
        with self.assertLogs("pipeworks.embedded.cuda_async", level="ERROR"):
            outputs = list(CudaAsync(inner, timeout_ms=1000).process(iter(frames)))
        self.assertIs(outputs[0], frames[0])
        self.assertEqual(frames[0].data, [1])
        self.assertEqual(frames[1].data, [1, 2])
        self.assertEqual(inner.starts, 2)

    def test_new_output_context_is_applied_to_original(self):
        original = PipelineContext(old=True)
        inner = FunctionStep(lambda item, _: PipelineContext(result=7))
        self.assertIs(list(CudaAsync(inner, timeout_ms=1000).process(iter([original])))[0], original)
        self.assertEqual(vars(original), {"result": 7})

    def test_success_shares_input_without_snapshot(self):
        data = [1]
        tensor = torch.tensor([1.0], requires_grad=True) * 2
        original = PipelineContext(data=data, left=tensor, right=tensor)

        def process(item, _):
            self.assertIs(item.left, item.right)
            self.assertIs(item.data, data)
            self.assertIs(item.left, tensor)
            item.data = item.data + [2]
            item.left = item.right = item.left + 3
            return item

        with patch.object(torch.Tensor, "clone", side_effect=AssertionError("input clone")) as snapshot:
            list(CudaAsync(FunctionStep(process), timeout_ms=1000).process(iter([original])))
        snapshot.assert_not_called()
        self.assertEqual(data, [1])
        self.assertEqual(tensor.tolist(), [2])
        self.assertEqual(original.data, [1, 2])
        self.assertEqual(original.left.tolist(), [5])
        self.assertIs(original.left, original.right)

    def test_late_completed_request_passes_without_signal_or_result(self):
        module = import_module('pipeworks.embedded.cuda_async')
        original = PipelineContext(frame=torch.tensor([1]))
        finish = module._InputSlot.finish
        def late_finish(slot, request, result):
            request.deadline = 0
            finish(slot, request, result)
        def process(item, index):
            item.late = True
            return item
        with patch.object(module._InputSlot, 'finish', late_finish), patch.object(
            torch.Tensor, 'clone', side_effect=AssertionError('input clone')
        ):
            outputs = list(CudaAsync(FunctionStep(process), timeout_ms=1000).process(iter([original])))
        self.assertEqual(outputs, [original])
        self.assertFalse(hasattr(original, 'late'))

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

        outputs = list(CudaAsync(inner, timeout_ms=1000).process(frames()))
        self.assertEqual([item.value for item in outputs], ["first", "second"])

    def test_close_does_not_wait_for_blocked_worker(self):
        release, closed = Event(), Event()
        self.addCleanup(release.set)

        class BlockingStep(Step):
            def configure(self, config):
                pass

            def process(self, inputs):
                try:
                    for item in inputs:
                        release.wait(5)
                        yield item
                finally:
                    closed.set()

        stream = CudaAsync(BlockingStep(), timeout_ms=10).process(iter([PipelineContext()]))
        self.assertEqual(list(stream), [])
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
            def configure(self, config):
                pass

            def process(self, inputs):
                try:
                    for item in inputs:
                        calls.append(item)
                        release.wait(5)
                        yield item
                finally:
                    closed.set()

        wrapper = CudaAsync(BlockingStep(), timeout_ms=10)
        first = wrapper.process(iter([PipelineContext()]))
        self.assertEqual(list(first), [])
        first.close()
        original = PipelineContext(value=1)
        self.assertIs(list(wrapper.process(iter([original])))[0], original)
        self.assertEqual(len(calls), 1)
        release.set()
        self.assertTrue(closed.wait(1))

    def test_wrapper_is_serializable_before_use(self):
        import cloudpickle

        wrapper = CudaAsync(FunctionStep(lambda item, _: PipelineContext(value=item.value + 1)), timeout_ms=1000)
        restored = cloudpickle.loads(cloudpickle.dumps(wrapper))
        output = list(restored.process(iter([PipelineContext(value=1)])))[0]
        self.assertEqual(output.value, 2)

    def test_uncloneable_input_succeeds_without_copy(self):
        class Uncloneable:
            def __deepcopy__(self, memo):
                raise TypeError("복사 불가")

        inner = FunctionStep(lambda item, _: item)
        original = PipelineContext(resource=Uncloneable())
        outputs = list(CudaAsync(inner, timeout_ms=1000).process(iter([original])))
        self.assertIs(outputs[0], original)
        self.assertEqual(inner.starts, 1)

    def test_timeout_never_deepcopies_input_or_waits_for_worker(self):
        class Uncloneable:
            def __deepcopy__(self, memo):
                raise AssertionError('deepcopy called')
        entered, unblock = Event(), Event()
        self.addCleanup(unblock.set)
        def process(item, index):
            entered.set()
            unblock.wait(5)
            return item
        original, following = PipelineContext(resource=Uncloneable()), PipelineContext(number=2)
        wrapper = CudaAsync(FunctionStep(process), timeout_ms=100)
        started = time.monotonic()
        self.assertEqual(list(wrapper.process(iter([original, following]))), [following])
        self.assertLess(time.monotonic() - started, .5)
        self.assertTrue(entered.is_set())
        unblock.set()
        self.assertTrue(wrapper._session_lock.acquire(timeout=1))
        wrapper._session_lock.release()

    def test_timeout_retains_original_storage_until_completion(self):
        import gc
        import weakref
        entered, unblock, reclaimed = Event(), Event(), Event()
        self.addCleanup(unblock.set)
        def process(item, index):
            entered.set()
            unblock.wait(5)
            self.assertEqual(item.tensor.tolist(), [1])
            return item
        tensor = torch.tensor([1])
        retained = weakref.ref(tensor, lambda ref: reclaimed.set())
        original = PipelineContext(tensor=tensor)
        wrapper = CudaAsync(FunctionStep(process), timeout_ms=100)
        self.assertEqual(list(wrapper.process(iter([original]))), [])
        self.assertTrue(entered.is_set())
        del tensor, original
        gc.collect()
        self.assertIsNotNone(retained())
        unblock.set()
        self.assertTrue(wrapper._session_lock.acquire(timeout=1))
        wrapper._session_lock.release()
        gc.collect()
        self.assertTrue(reclaimed.wait(1))

    def test_contract_violations_pass_original(self):
        class Aggregate(Step):
            def configure(self, config):
                pass

            def process(self, inputs):
                first = next(inputs)
                next(inputs)
                yield first

        class Source(Step):
            def configure(self, config):
                pass

            def process(self, inputs):
                yield PipelineContext(invalid=True)

        class Empty(Step):
            def configure(self, config):
                pass

            def process(self, inputs):
                for _ in inputs:
                    return
                yield

        for inner in (Aggregate(), Source(), Empty()):
            original = PipelineContext(value=1)
            with self.subTest(inner=type(inner).__name__), self.assertLogs("pipeworks.embedded.cuda_async", level="ERROR"):
                outputs = list(CudaAsync(inner, timeout_ms=1000).process(iter([original])))
            self.assertIs(outputs[0], original)
            self.assertEqual(vars(original), {"value": 1})

    def test_zero_timeout_drops_frame_while_worker_runs(self):
        release, entered = Event(), Event()
        self.addCleanup(release.set)

        def process(item, _):
            entered.set()
            release.wait(5)
            item.changed = True
            return item

        original = PipelineContext()
        stream = CudaAsync(FunctionStep(process), timeout_ms=0).process(iter([original]))
        self.assertEqual(list(stream), [])
        self.assertTrue(entered.wait(1))
        self.assertEqual(vars(original), {})
        stream.close()
        release.set()

    def test_pipeline_applies_async_and_inner_configuration(self):
        from pipeworks import Pipeline

        with TemporaryDirectory() as directory:
            config = Path(directory) / "stream.yml"
            config.write_text("CudaAsync:\n  timeout_ms: 100\nFunctionStep:\n  confidence: 0.4\n", encoding="utf-8")
            inner = FunctionStep(lambda item, _: item)
            wrapper = CudaAsync(inner)
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
            print("CudaAsync 작업자 출력")
            return item

        with patch("sys.stdout", output):
            list(CudaAsync(FunctionStep(process), timeout_ms=1000).process(iter([PipelineContext()])))
        self.assertIn("CudaAsync 작업자 출력", "".join(writes))

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

        pipeline = SimpleNamespace(steps=[CudaAsync(FunctionStep(lambda item, _: item))])
        with patch.object(main, "_connect", return_value=Connection()), \
                patch.object(main.cloudpickle, "register_pickle_by_value") as register, \
                patch.object(main.cloudpickle, "dumps", return_value=b"pipeline"):
            main.run_remote(pipeline)
        register.assert_called_once_with(sys.modules[FunctionStep.__module__])

    def test_remote_serializes_all_nested_user_steps_without_modules(self):
        import sys
        from types import ModuleType
        import pipeworks.main as main
        from pipeworks.embedded import Tap

        modules = [ModuleType("async_remote_first"), ModuleType("async_remote_second")]
        for module in modules:
            exec("from pipeworks.models import Step\nclass Custom(Step):\n    def configure(self, config):\n        pass\n    def process(self, inputs):\n        yield from inputs\n", module.__dict__)
            sys.modules[module.__name__] = module
        payloads = []

        class Connection:
            def send_bytes(self, payload):
                payloads.append(payload)

            def recv(self):
                return ("ok", None)

            def close(self):
                pass

        try:
            pipeline = SimpleNamespace(steps=[Tap(CudaAsync(modules[0].Custom(), CudaAsync(modules[1].Custom())))])
            with patch.object(main, "_connect", return_value=Connection()):
                main.run_remote(pipeline)
            for module in modules:
                sys.modules.pop(module.__name__)
            restored = main.cloudpickle.loads(payloads[0])
            self.assertEqual(len(restored.steps[0].step.steps), 2)
        finally:
            for module in modules:
                try:
                    main.cloudpickle.unregister_pickle_by_value(module)
                except ValueError:
                    pass
                sys.modules.pop(module.__name__, None)

    @unittest.skipUnless(torch.cuda.is_available(), 'CUDA required')
    def test_gpu_timeout_before_release_drops_without_clone(self):
        unblock = Event()
        self.addCleanup(unblock.set)
        stream = torch.cuda.Stream()
        with torch.cuda.stream(stream):
            tensor = torch.ones((6, 4), dtype=torch.uint8, device='cuda')
        def process(item, index):
            unblock.wait(5)
            return item
        wrapper = CudaAsync(FunctionStep(process), timeout_ms=100)
        original = PipelineContext(frame=tensor, cuda_stream=stream)
        with patch.object(torch.Tensor, 'clone', side_effect=AssertionError('input clone')):
            self.assertEqual(list(wrapper.process(iter([original]))), [])
        self.assertIs(original.frame, tensor)
        unblock.set()
        self.assertTrue(wrapper._session_lock.acquire(timeout=2))
        wrapper._session_lock.release()

    @unittest.skipUnless(torch.cuda.is_available(), "CUDA required")
    def test_gpu_success_uses_dlpack_without_copy(self):
        stream = torch.cuda.Stream()
        with torch.cuda.stream(stream):
            tensor = torch.ones((6, 4), dtype=torch.uint8, device="cuda")

        class Frame:
            def __dlpack__(self, stream=None):
                return tensor.__dlpack__(stream=stream)

            def __dlpack_device__(self):
                return tensor.__dlpack_device__()

        def process(item, _):
            self.assertEqual(item.frame.data_ptr(), tensor.data_ptr())
            self.assertIs(item.model_input, tensor)
            item.answer = 7
            return item

        original = PipelineContext(frame=Frame(), model_input=tensor, cuda_stream=stream)
        with patch.object(torch.Tensor, "clone", side_effect=AssertionError("input clone")) as snapshot, patch.object(
            torch.Tensor, "cpu", side_effect=AssertionError("CPU 전송 금지")
        ):
            output = list(CudaAsync(FunctionStep(process), timeout_ms=1000).process(iter([original])))[0]
        snapshot.assert_not_called()
        self.assertIs(output, original)
        self.assertEqual(output.answer, 7)
        self.assertEqual(output.frame.data_ptr(), tensor.data_ptr())

    @unittest.skipUnless(torch.cuda.is_available(), 'CUDA required')
    def test_gpu_dlpack_frame_is_retained_without_copy_on_drop(self):
        unblock, done = Event(), Event()
        self.addCleanup(unblock.set)
        stream = torch.cuda.Stream()
        with torch.cuda.stream(stream):
            tensor = torch.ones((6, 4), dtype=torch.uint8, device='cuda')
        class Frame:
            def __dlpack__(self, stream=None):
                return tensor.__dlpack__(stream=stream)
            def __dlpack_device__(self):
                return tensor.__dlpack_device__()
        frame = Frame()
        def process(item, index):
            unblock.wait(5)
            self.assertEqual(item.frame.data_ptr(), tensor.data_ptr())
            with torch.cuda.stream(item.cuda_stream):
                self.assertTrue(torch.all(item.frame == 1).item())
            done.set()
            return item
        wrapper = CudaAsync(FunctionStep(process), timeout_ms=100)
        original = PipelineContext(frame=frame, cuda_stream=stream)
        with patch.object(torch.Tensor, 'clone', side_effect=AssertionError('input clone')):
            self.assertEqual(list(wrapper.process(iter([original]))), [])
        self.assertIs(original.frame, frame)
        unblock.set()
        self.assertTrue(wrapper._session_lock.acquire(timeout=2))
        wrapper._session_lock.release()
        self.assertTrue(done.is_set())
