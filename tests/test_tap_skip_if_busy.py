import gc
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import ModuleType
import unittest
from uuid import uuid4
import weakref

from pipeworks.embedded.tap_skip_if_busy import TapSkipIfBusy, _InputSlot
from pipeworks.hotswap import Hotswap
from pipeworks.models import PipelineContext, Step


class Accumulator(Step):
    def __init__(self):
        self.total = 0

    def configure(self, config):
        pass

    def process(self, inputs):
        for item in inputs:
            self.total += item.value
            yield PipelineContext(value=self.total)


class TapBranchTests(unittest.TestCase):
    def test_background_reload_preserves_foreground_accumulation(self):
        def code(version):
            return f"""from pipeworks.models import Step
class Background(Step):
    version = {version}
    def configure(self, config): pass
    def process(self, inputs):
        yield from inputs
"""

        with TemporaryDirectory() as directory:
            path = Path(directory) / "background.py"
            path.write_text(code(1), encoding="utf-8")
            module = ModuleType("tap_reload_" + uuid4().hex)
            module.__file__, module.__package__ = str(path), ""
            sys.modules[module.__name__] = module
            self.addCleanup(sys.modules.pop, module.__name__, None)
            exec(compile(code(1), str(path), "exec"), module.__dict__)
            background = Hotswap(module.Background(), check_interval=0)
            foreground = Hotswap(Accumulator(), watch_code=False)
            slot = _InputSlot()

            def inputs():
                yield PipelineContext(value=1)
                path.write_text(code(2), encoding="utf-8")
                self.assertTrue(background._commit_update())
                original = PipelineContext(value=2)
                self.assertTrue(slot.offer(original))
                # 분기 쪽의 변경 표시를 먼저 기록하도록 실행 순서를 고정한다.
                list(background.process(iter([next(slot)])))
                yield original

            result = list(foreground.process(inputs()))
            self.assertEqual(background.wrapped_step.version, 2)
            self.assertEqual([item.value for item in result], [1, 3])

    def test_top_level_attributes_and_epochs_are_isolated_both_ways(self):
        original = PipelineContext(value=1, frame=object(), nested={"shared": True})
        original._pipeworks_hotswap_epoch = ((100, 1),)
        slot = _InputSlot()
        self.assertTrue(slot.offer(original))
        branch = next(slot)
        self.assertIsNot(branch, original)
        original.value = 2
        original._pipeworks_hotswap_epoch = ((100, 2),)
        self.assertEqual(branch.value, 1)
        self.assertEqual(branch._pipeworks_hotswap_epoch, ((100, 1),))
        branch.value = 3
        branch.added = True
        del branch.frame
        branch._pipeworks_hotswap_epoch += ((200, 1),)
        self.assertEqual(original.value, 2)
        self.assertFalse(hasattr(original, "added"))
        self.assertTrue(hasattr(original, "frame"))
        self.assertEqual(original._pipeworks_hotswap_epoch, ((100, 2),))
        self.assertIs(branch.nested, original.nested)

    def test_common_upstream_epoch_is_preserved_by_background_hotswap(self):
        class PassThrough(Step):
            def configure(self, config):
                pass

            def process(self, inputs):
                yield from inputs

        original = PipelineContext(_pipeworks_hotswap_epoch=((10, 1),))
        slot = _InputSlot()
        slot.offer(original)
        background = Hotswap(PassThrough(), watch_code=False)
        outputs = list(background.process(iter([next(slot)])))
        self.assertEqual(outputs[0]._pipeworks_hotswap_epoch, ((10, 1),))
        self.assertEqual(original._pipeworks_hotswap_epoch, ((10, 1),))

    def test_actual_tap_preserves_original_output_and_shared_resources(self):
        class SharedResource:
            def __deepcopy__(self, memo):
                raise AssertionError("공유 자원을 깊은 복사하면 안 됩니다.")

            def clone(self):
                raise AssertionError("공유 버퍼를 복제하면 안 됩니다.")

        observed, closed = [], []

        class MutateAttributes(Step):
            def configure(self, config):
                pass

            def process(self, inputs):
                try:
                    for item in inputs:
                        observed.append(item)
                        item.value = "background"
                        item.background_only = True
                        yield item
                finally:
                    closed.append(True)

        resources = {name: SharedResource() for name in (
            "frame", "packet", "cuda_stream", "video_stream", "_decode_buffer",
        )}
        original = PipelineContext(value="original", **resources)
        background = Hotswap(MutateAttributes(), watch_code=False)
        output = list(TapSkipIfBusy(background).process(iter([original])))
        self.assertEqual(closed, [True])
        self.assertIs(output[0], original)
        self.assertIsNot(observed[0], original)
        self.assertEqual(original.value, "original")
        self.assertFalse(hasattr(original, "background_only"))
        self.assertFalse(hasattr(original, "_pipeworks_hotswap_epoch"))
        for name, resource in resources.items():
            self.assertIs(getattr(observed[0], name), resource)

    def test_busy_or_closed_slot_does_not_copy_rejected_input(self):
        class RejectedInput(PipelineContext):
            def __getattribute__(self, name):
                if name == "__dict__":
                    raise AssertionError("생략한 입력의 속성을 복사하면 안 됩니다.")
                return super().__getattribute__(name)

        slot = _InputSlot()
        self.assertTrue(slot.offer(PipelineContext(value=1)))
        self.assertFalse(slot.offer(RejectedInput()))
        self.assertEqual(next(slot).value, 1)
        slot.close()
        self.assertFalse(slot.offer(RejectedInput()))
        with self.assertRaises(StopIteration):
            next(slot)

    def test_background_snapshot_retains_decoder_owner(self):
        class Owner:
            pass

        owner = Owner()
        reference = weakref.ref(owner)
        original = PipelineContext(_decode_buffer=owner)
        slot = _InputSlot()
        slot.offer(original)
        del owner, original._decode_buffer
        gc.collect()
        self.assertIsNotNone(reference())
        branch = next(slot)
        del branch
        gc.collect()
        self.assertIsNone(reference())


if __name__ == "__main__":
    unittest.main()
