import unittest
from types import SimpleNamespace

from pipeworks.embedded import RunOnce
from pipeworks.models import PipelineContext, Step


class RecordingStep(Step):
    def __init__(self, calls, *, multiple=False):
        self.calls = calls
        self.multiple = multiple

    def configure(self, config):
        pass

    def process(self, inputs):
        self.calls.append("process")
        for item in inputs:
            yield PipelineContext(value=item.value + 10)
            if self.multiple:
                yield PipelineContext(value=item.value + 20)


class FailingStep(Step):
    def __init__(self, calls):
        self.calls = calls

    def configure(self, config):
        pass

    def process(self, inputs):
        self.calls.append("process")
        next(iter(inputs))
        raise ValueError("first run failed")
        yield


class ConfigurableStep(RecordingStep):
    def configure(self, config):
        self.offset = config.offset

    def process(self, inputs):
        self.calls.append("process")
        for item in inputs:
            yield PipelineContext(value=item.value + self.offset)


class RunOnceTests(unittest.TestCase):
    def contexts(self, *values):
        return [PipelineContext(value=value) for value in values]

    def test_runs_inner_step_for_first_input_and_passes_through_remaining_inputs(self):
        calls = []
        original = self.contexts(1, 2, 3)

        output = list(RunOnce(RecordingStep(calls)).process(iter(original)))

        self.assertEqual([item.value for item in output], [11, 2, 3])
        self.assertEqual(calls, ["process"])

    def test_empty_input_does_not_run_inner_step(self):
        calls = []

        output = list(RunOnce(RecordingStep(calls)).process(iter(())))

        self.assertEqual(output, [])
        self.assertEqual(calls, [])

    def test_forwards_all_outputs_from_first_inner_run(self):
        calls = []

        output = list(
            RunOnce(RecordingStep(calls, multiple=True)).process(
                iter(self.contexts(1, 2))
            )
        )

        self.assertEqual([item.value for item in output], [11, 21, 2])
        self.assertEqual(calls, ["process"])

    def test_successful_instance_does_not_run_inner_step_on_next_process_call(self):
        calls = []
        wrapper = RunOnce(RecordingStep(calls))

        first = list(wrapper.process(iter(self.contexts(1, 2))))
        second = list(wrapper.process(iter(self.contexts(3, 4))))

        self.assertEqual([item.value for item in first], [11, 2])
        self.assertEqual([item.value for item in second], [3, 4])
        self.assertEqual(calls, ["process"])

    def test_inner_failure_is_propagated_and_can_be_retried(self):
        calls = []
        wrapper = RunOnce(FailingStep(calls))

        with self.assertRaisesRegex(ValueError, "first run failed"):
            list(wrapper.process(iter(self.contexts(1))))
        with self.assertRaisesRegex(ValueError, "first run failed"):
            list(wrapper.process(iter(self.contexts(2))))

        self.assertEqual(calls, ["process", "process"])

    def test_instances_do_not_share_completion_state(self):
        calls = []
        first = RunOnce(RecordingStep(calls))
        second = RunOnce(RecordingStep(calls))

        list(first.process(iter(self.contexts(1))))
        list(second.process(iter(self.contexts(2))))

        self.assertEqual(calls, ["process", "process"])

    def test_requires_a_step(self):
        with self.assertRaises(TypeError):
            RunOnce(object())

    def test_is_exported_as_embedded_step(self):
        from pipeworks.embedded.run_once import RunOnce as ConcreteRunOnce

        self.assertIs(RunOnce, ConcreteRunOnce)
        self.assertIsInstance(RunOnce(RecordingStep([])), Step)

    def test_exposes_inner_step_for_pipeline_configuration_and_discovery(self):
        calls = []
        inner = ConfigurableStep(calls)
        wrapper = RunOnce(inner)

        wrapper._hot_steps[0].configure(SimpleNamespace(offset=7))
        output = list(wrapper.process(iter(self.contexts(1, 2))))

        self.assertEqual([item.value for item in output], [8, 2])
        self.assertEqual(calls, ["process"])

    def test_pipeline_step_discovery_includes_wrapper_and_inner_step(self):
        from pipeworks.pipeline import _iter_steps

        inner = RecordingStep([])
        wrapper = RunOnce(inner)

        discovered = list(_iter_steps([wrapper]))

        self.assertIn(wrapper, discovered)
        self.assertIn(inner, discovered)


if __name__ == "__main__":
    unittest.main()
