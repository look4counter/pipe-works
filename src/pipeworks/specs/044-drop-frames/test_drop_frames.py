from types import SimpleNamespace
import unittest

from pipeworks.embedded import DropFrames
from pipeworks.models import PipelineContext


class DropFramesTests(unittest.TestCase):
    def test_selection_preserves_objects_and_metadata(self):
        items = [PipelineContext(frame=i, pts=i * 10) for i in range(6)]
        for interval, expected in ((1, [0, 1, 2, 3, 4, 5]), (2, [0, 2, 4]),
                                   (3, [0, 3]), (10, [0])):
            with self.subTest(interval=interval):
                result = list(DropFrames(keep_every=interval).process(iter(items)))
                self.assertEqual([item.frame for item in result], expected)
                for item, index in zip(result, expected):
                    self.assertIs(item, items[index])
                    self.assertEqual(vars(item), {"frame": index, "pts": index * 10})

    def test_defaults_empty_input_and_reuse(self):
        items = [PipelineContext(frame=i) for i in range(3)]
        self.assertEqual(list(DropFrames().process(iter(items))), items)
        step = DropFrames(keep_every=2)
        self.assertEqual(list(step.process(iter([]))), [])
        for _ in range(2):
            self.assertEqual(list(step.process(iter(items))), [items[0], items[2]])

    def test_configuration_overrides_and_restores_constructor_default(self):
        step = DropFrames(keep_every=2)
        step.configure(SimpleNamespace(keep_every=3))
        self.assertEqual(step.keep_every, 3)
        step.configure(SimpleNamespace())
        self.assertEqual(step.keep_every, 2)

    def test_invalid_intervals_are_rejected(self):
        for value in (0, -1, 1.5, True, False, "2", None):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "keep_every"):
                    DropFrames(keep_every=value)
                with self.assertRaisesRegex(ValueError, "keep_every"):
                    DropFrames().configure(SimpleNamespace(keep_every=value))

    def test_downstream_receives_only_selected_frames(self):
        inferred, encoded = [], []

        def inference(inputs):
            for item in inputs:
                inferred.append(item.frame)
                yield item

        def encode(inputs):
            for item in inputs:
                encoded.append(item.frame)
                yield item

        items = (PipelineContext(frame=i) for i in range(6))
        list(encode(inference(DropFrames(keep_every=2).process(items))))
        self.assertEqual(inferred, [0, 2, 4])
        self.assertEqual(encoded, inferred)
