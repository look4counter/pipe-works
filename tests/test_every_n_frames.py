import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pipeworks import Pipeline
from pipeworks.embedded import EveryNFrames, CudaAsync, StreamReport
from pipeworks.hotswap import Hotswap
from pipeworks.models import PipelineContext, Step
from pipeworks.pipeline import _has_stream_report, _watch_async_children, _LiveConfig


class RecordingStep(Step):
    def __init__(self, name="work", offset=1):
        self.name = name
        self.calls = []
        self.started = self.finished = 0
        self._set_config_defaults(offset=offset)

    def configure(self, config):
        self.offset = self._resolve_config(config).offset

    def process(self, inputs):
        self.started += 1
        try:
            for item in inputs:
                self.calls.append(item.index)
                item.value += self.offset
                yield item
        finally:
            self.finished += 1


class EveryNFramesTests(unittest.TestCase):
    def items(self, count=7):
        return [PipelineContext(index=i, value=0) for i in range(count)]

    def test_generic_group_skips_without_modifying_context(self):
        first, second = RecordingStep(), RecordingStep(offset=10)
        wrapper = EveryNFrames(first, second, interval_frames=3)
        items = self.items()
        skipped = {i: vars(items[i]).copy() for i in (1, 2, 4, 5)}
        output = list(wrapper.process(iter(items)))
        self.assertEqual(output, items)
        self.assertTrue(all(a is b for a, b in zip(output, items)))
        self.assertEqual(first.calls, [0, 3, 6])
        self.assertEqual(second.calls, first.calls)
        self.assertEqual([items[i].value for i in (0, 3, 6)], [11] * 3)
        for i, fields in skipped.items():
            self.assertEqual(vars(items[i]), fields)
        self.assertEqual((first.started, first.finished), (1, 1))
        self.assertEqual((second.started, second.finished), (1, 1))

    def test_async_drop_keeps_skips_and_busy_frames_without_extra_preparation(self):
        from threading import Event
        from unittest.mock import patch
        from pipeworks.embedded import cuda_async
        entered, unblock = Event(), Event()
        class HoldsFrame(RecordingStep):
            def process(self, inputs):
                for item in inputs:
                    entered.set()
                    unblock.wait(2)
                    yield item
        async_step = CudaAsync(HoldsFrame(), timeout_ms=50)
        after = RecordingStep()
        wrapper = EveryNFrames(async_step, after, interval_frames=3)
        items = self.items()
        skipped = {i: vars(items[i]).copy() for i in (1, 2, 4, 5)}
        try:
            with patch.object(cuda_async, "_prepare", wraps=cuda_async._prepare) as prepare:
                output = list(wrapper.process(iter(items)))
            self.assertTrue(entered.is_set())
            self.assertEqual([item.index for item in output], [1, 2, 3, 4, 5, 6])
            self.assertEqual(after.calls, [3, 6])
            self.assertEqual(prepare.call_count, 1)
            for i, fields in skipped.items():
                self.assertEqual(vars(items[i]), fields)
                self.assertIs(output[i - 1], items[i])
        finally:
            unblock.set()
            self.assertTrue(async_step._session_lock.acquire(timeout=2))
            async_step._session_lock.release()

    def test_async_drop_then_recovery_reuses_worker_and_input_counter(self):
        from threading import Event
        from unittest.mock import patch
        from pipeworks.embedded import cuda_async
        entered, unblock, finished = Event(), Event(), Event()
        child = RecordingStep()
        def process(inputs):
            child.started += 1
            for item in inputs:
                child.calls.append(item.index)
                if item.index == 0:
                    entered.set()
                    unblock.wait(2)
                item.value += 10
                yield item
        child.process = process
        async_step = CudaAsync(child, timeout_ms=100)
        wrapper = EveryNFrames(async_step, interval_frames=3)
        finish = cuda_async._InputSlot.finish
        def notify(slot, request, result):
            finish(slot, request, result)
            finished.set()
        output = wrapper.process(iter(self.items()))
        try:
            with patch.object(cuda_async._InputSlot, "finish", notify):
                first = next(output)
                self.assertTrue(entered.is_set())
                self.assertEqual(first.index, 1)
                unblock.set()
                self.assertTrue(finished.wait(2))
                remaining = list(output)
            self.assertEqual([item.index for item in remaining], [2, 3, 4, 5, 6])
            self.assertEqual(child.calls, [0, 3, 6])
            self.assertEqual(child.started, 1)
            self.assertEqual([item.value for item in remaining if item.index in (3, 6)], [10, 10])
        finally:
            unblock.set()
            output.close()
            self.assertTrue(async_step._session_lock.acquire(timeout=2))
            async_step._session_lock.release()

    def test_last_async_input_can_be_dropped(self):
        from threading import Event
        unblock = Event()
        class HoldsFrame(RecordingStep):
            def process(self, inputs):
                for item in inputs:
                    unblock.wait(2)
                    yield item
        async_step = CudaAsync(HoldsFrame(), timeout_ms=50)
        try:
            self.assertEqual(list(EveryNFrames(async_step).process(iter(self.items(1)))), [])
        finally:
            unblock.set()
            self.assertTrue(async_step._session_lock.acquire(timeout=2))
            async_step._session_lock.release()

    def test_safe_async_timeout_returns_original_to_following_step(self):
        from threading import Event
        from pipeworks.execution import release_frame
        unblock = Event()
        class SafeSlow(RecordingStep):
            def process(self, inputs):
                for item in inputs:
                    release_frame()
                    unblock.wait(2)
                    yield item
        async_step = CudaAsync(SafeSlow(), timeout_ms=50)
        following = RecordingStep()
        try:
            output = list(EveryNFrames(async_step, following, interval_frames=3).process(iter(self.items())))
            self.assertEqual([item.index for item in output], list(range(7)))
            self.assertEqual(following.calls, [0, 3, 6])
        finally:
            unblock.set()
            self.assertTrue(async_step._session_lock.acquire(timeout=2))
            async_step._session_lock.release()

    def test_pipeline_watchers_preserve_async_drop_protocol(self):
        from threading import Event
        unblock = Event()
        items = self.items(4)
        class Source(Step):
            def configure(self, config): pass
            def process(self, inputs): yield from items
        class HoldsFrame(RecordingStep):
            def process(self, inputs):
                for item in inputs:
                    unblock.wait(2)
                    yield item
        async_step = CudaAsync(HoldsFrame(), timeout_ms=50)
        sink = RecordingStep()
        try:
            with tempfile.TemporaryDirectory() as temporary:
                config = Path(temporary) / "stream.yml"
                config.write_text("EveryNFrames:\n  interval_frames: 3\nCudaAsync:\n  timeout_ms: 50\n", encoding="utf-8")
                pipeline = Pipeline("drop-watch", config=config).step(Source()).step(EveryNFrames(async_step)).step(sink)
                pipeline._run_local()
            self.assertEqual(sink.calls, [1, 2, 3])
        finally:
            unblock.set()
            self.assertTrue(async_step._session_lock.acquire(timeout=2))
            async_step._session_lock.release()

    def test_default_and_independent_runs(self):
        child = RecordingStep()
        wrapper = EveryNFrames(child)
        list(wrapper.process(iter(self.items(3))))
        wrapper.configure(SimpleNamespace(interval_frames=2))
        list(wrapper.process(iter(self.items(3))))
        list(wrapper.process(iter(self.items(3))))
        self.assertEqual(child.calls, [0, 1, 2, 0, 2, 0, 2])
        wrapper.configure(SimpleNamespace())
        self.assertEqual(wrapper.interval_frames, 1)

    def test_empty_input_does_not_start_child(self):
        child = RecordingStep()
        self.assertEqual(list(EveryNFrames(child).process(iter(()))), [])
        self.assertEqual(child.started, 0)

    def test_validation(self):
        with self.assertRaises(TypeError):
            EveryNFrames()
        with self.assertRaises(TypeError):
            EveryNFrames(RecordingStep(), object())
        for value in (0, -1, True, 1.5, "3", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                EveryNFrames(RecordingStep(), interval_frames=value)
        wrapper = EveryNFrames(RecordingStep(), interval_frames=3)
        with self.assertRaises(ValueError):
            wrapper.configure(SimpleNamespace(interval_frames=0))
        self.assertEqual(wrapper.interval_frames, 3)
        with self.assertRaises(ValueError):
            wrapper.configure(SimpleNamespace(other=1))

    def test_early_close_closes_children_and_upstream(self):
        child, closed = RecordingStep(), []
        def source():
            try:
                yield from self.items()
            finally:
                closed.append(True)
        output = EveryNFrames(child, interval_frames=3).process(source())
        next(output)
        output.close()
        self.assertEqual(child.finished, 1)
        self.assertEqual(closed, [True])

    def test_failure_keeps_video_and_closes_stages_at_end(self):
        first = RecordingStep()
        class Fails(RecordingStep):
            def process(self, inputs):
                next(inputs)
                raise ValueError("failure")
                yield
        items = self.items()
        self.assertEqual(list(EveryNFrames(first, Fails()).process(iter(items))), items)
        self.assertEqual(first.finished, 1)

    def test_invalid_child_input_output_contracts(self):
        def no_output(inputs):
            next(inputs)
            return
            yield
        def prefetch(inputs):
            next(inputs)
            yield next(inputs)
        def no_consume(inputs):
            yield PipelineContext()
        def bad_type(inputs):
            next(inputs)
            yield None
        def duplicate(inputs):
            for item in inputs:
                yield item
                yield item
        for function in (no_output, prefetch, no_consume, bad_type, duplicate):
            with self.subTest(function=function.__name__):
                child = RecordingStep()
                child.process = function
                wrapper = EveryNFrames(child)
                wrapper._hot_steps = (child,)
                items = self.items(1)
                self.assertEqual(list(wrapper.process(iter(items))), items)

    def test_live_interval_change_uses_accumulated_input_index(self):
        child = RecordingStep()
        wrapper = EveryNFrames(child, interval_frames=3)
        output = wrapper.process(iter(self.items()))
        next(output)
        next(output)
        wrapper.configure(SimpleNamespace(interval_frames=2))
        list(output)
        self.assertEqual(child.calls, [0, 2, 4, 6])

    def test_nested_yaml_and_watchers(self):
        child = RecordingStep(offset=2)
        inner = EveryNFrames(child, interval_frames=3)
        outer = CudaAsync(inner, timeout_ms=1000)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "stream.yml"
            path.write_text("EveryNFrames:\n  interval_frames: 2\nRecordingStep:\n  offset: 7\n", encoding="utf-8")
            pipeline = Pipeline("nested", config=path).step(outer)
            self.assertEqual((inner.interval_frames, child.offset), (2, 7))
            watcher = _LiveConfig(path, vars(pipeline.config), pipeline._config_digest)
            try:
                _watch_async_children(outer, watcher, vars(pipeline.config))
                path.write_text("EveryNFrames:\n  interval_frames: 4\nRecordingStep:\n  offset: 9\n", encoding="utf-8")
                watcher.last_check = float("-inf")
                outer._hot_steps[0]._check_for_update(force=True)
                watcher.last_check = float("-inf")
                inner._hot_steps[0]._check_for_update(force=True)
                self.assertEqual((inner.interval_frames, child.offset), (4, 9))
            finally:
                watcher.close()

    def test_internal_code_hotswap_preserves_group_counter(self):
        from types import ModuleType
        def code(offset):
            return (
                "from pipeworks.models import Step\n"
                "class Changing(Step):\n"
                "    def configure(self, config): pass\n"
                "    def process(self, inputs):\n"
                "        for item in inputs:\n"
                f"            item.value += {offset}\n"
                "            yield item\n"
            )
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "changing.py"
            path.write_text(code(1), encoding="utf-8")
            module = ModuleType("frames_changing_test")
            module.__file__ = str(path)
            sys.modules[module.__name__] = module
            try:
                exec(compile(code(1), str(path), "exec"), module.__dict__)
                wrapper = EveryNFrames(module.Changing(), interval_frames=2)
                wrapper._hot_steps[0].check_interval = 0
                output = wrapper.process(iter(self.items(3)))
                try:
                    self.assertEqual(next(output).value, 1)
                    path.write_text(code(10), encoding="utf-8")
                    wrapper._hot_steps[0]._file_subscription._service.mark_changed(path)
                    self.assertEqual(next(output).value, 0)
                    self.assertEqual(next(output).value, 10)
                finally:
                    output.close()
            finally:
                sys.modules.pop(module.__name__, None)

    def test_cuda_async_nested_inference_uses_backend_status(self):
        from threading import Event
        from pipeworks.embedded import Backend, YoloInference
        from pipeworks.embedded.stream_report import report_scope
        from pipeworks.embedded.yolo_report import begin, store
        from pipeworks.execution import release_frame
        unblock = Event()
        class Slow(YoloInference):
            def process(self, inputs):
                for item in inputs:
                    profile = begin(self.report_kind)
                    release_frame()
                    unblock.wait(2)
                    profile.finish()
                    yield item
        wrapper = CudaAsync(EveryNFrames(Slow("model.pt", backend=Backend.TENSORRT)), timeout_ms=50)
        with report_scope():
            stats = store()
            stats.activate("TensorRT")
            try:
                self.assertEqual(len(list(wrapper.process(iter([PipelineContext()])))), 1)
            finally:
                unblock.set()
                self.assertTrue(wrapper._session_lock.acquire(timeout=2))
                wrapper._session_lock.release()
            self.assertEqual(stats.snapshot("TensorRT", 0)["states"].get("timeout"), 1)

    def test_report_nested_in_wrapper(self):
        self.assertTrue(_has_stream_report([EveryNFrames(StreamReport())]))

    def test_cuda_async_can_wrap_generic_group(self):
        child = RecordingStep()
        items = self.items(4)
        output = list(CudaAsync(EveryNFrames(child, interval_frames=2), timeout_ms=1000).process(iter(items)))
        self.assertEqual(len(output), 4)
        self.assertEqual(child.calls, [0, 2])


if __name__ == "__main__":
    unittest.main()
