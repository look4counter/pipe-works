import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pipeworks.models import PipelineContext, Step


class PipelineContextTests(unittest.TestCase):
    def test_pass_through_preserves_dynamic_fields_but_new_context_does_not(self):
        class PassThrough(Step):
            def configure(self, config):
                pass

            def process(self, inputs):
                for item in inputs:
                    yield item

        class Replace(Step):
            def configure(self, config):
                pass

            def process(self, inputs):
                for item in inputs:
                    yield PipelineContext(value=item.value)

        original = PipelineContext(value=1, custom="keep")
        passed = next(PassThrough().process(iter([original])))
        self.assertIs(passed, original)
        self.assertEqual(passed.custom, "keep")
        replaced = next(Replace().process(iter([passed])))
        self.assertIsNot(replaced, original)
        self.assertFalse(hasattr(replaced, "custom"))

    def test_empty_context_has_no_fixed_fields(self):
        context = PipelineContext()
        self.assertIsInstance(context, SimpleNamespace)
        self.assertEqual(vars(context), {})
        self.assertFalse(hasattr(context, "packet"))
        self.assertFalse(hasattr(context, "video_stream"))

    def test_dynamic_attributes(self):
        context = PipelineContext(step_name="RTSPSource")
        self.assertEqual(context.step_name, "RTSPSource")
        context.frame_number = 3
        self.assertEqual(context.frame_number, 3)

    def test_source_can_define_packet_fields(self):
        stream = object()
        packet = object()
        context = PipelineContext(video_stream=stream, packet=packet)
        self.assertIs(context.video_stream, stream)
        self.assertIs(context.packet, packet)


if __name__ == "__main__":
    unittest.main()
