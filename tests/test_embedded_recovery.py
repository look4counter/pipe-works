from types import SimpleNamespace
from threading import Event
import unittest
from unittest.mock import Mock, patch

from pipeworks import Backend
from pipeworks.embedded import CudaAsync, EveryNFrames, RTSPSource, TapSkipIfBusy, YoloInference
from pipeworks.embedded.recovery import ResourceSafetyError, gpu_call, is_fatal
from pipeworks.models import PipelineContext, Step


class RecoveryTests(unittest.TestCase):
    def test_gpu_classification_preserves_causes_and_general_runtime_errors(self):
        for error in (ValueError("bad shape"), RuntimeError("model failed")):
            self.assertFalse(is_fatal(error))
        wrapped = ValueError("wrapper")
        wrapped.__cause__ = RuntimeError("CUDA error: device-side assert triggered")
        self.assertTrue(is_fatal(wrapped))
        self.assertTrue(is_fatal(MemoryError()))
        with self.assertRaises(ResourceSafetyError):
            gpu_call(Mock(side_effect=RuntimeError("synchronize failed")))

    def test_direct_inference_restarts_failed_generator_in_all_modes(self):
        for backend in (Backend.TORCHSCRIPT, Backend.TENSORRT):
            for batch in (True, False):
                with self.subTest(backend=backend, batch=batch):
                    step = YoloInference("model.pt", backend=backend, batch=batch)
                    starts = []
                    items = [PipelineContext(frame=object(), value=i) for i in range(4)]

                    def process(inputs):
                        starts.append(True)
                        for item in inputs:
                            item.model_output = "stale"
                            if item.value in (1, 2):
                                raise ValueError("bad model output")
                            item.model_output = item.value
                            yield item

                    method = ("_process_tensor_rt_profiled" if backend == Backend.TENSORRT
                              else "_process_yolo")
                    with patch.object(step, method, side_effect=process):
                        result = list(step.process(iter(items)))
                    self.assertEqual(result, items)
                    self.assertEqual([i.model_output for i in result], [0, None, None, 3])
                    self.assertEqual(len(starts), 3)

    def test_direct_inference_gpu_failure_propagates(self):
        step = YoloInference("model.pt", backend=Backend.TORCHSCRIPT)

        def process(inputs):
            next(inputs)
            raise RuntimeError("CUDA error: illegal memory access")
            yield

        with patch.object(step, "_process_yolo", side_effect=process):
            with self.assertRaisesRegex(RuntimeError, "CUDA error"):
                list(step.process(iter([PipelineContext(frame=object())])))

    def test_inference_initialization_failure_keeps_postprocess_identity(self):
        step = YoloInference("model.pt", backend=Backend.TENSORRT)
        items = [PipelineContext(frame=object()) for _ in range(2)]
        with patch.object(step, "_process_tensor_rt_profiled",
                          side_effect=ValueError("session configuration unavailable")):
            self.assertEqual(list(step.process(iter(items))), items)
        self.assertTrue(all(i.model_output is None and i.model_id == step.id for i in items))

    def test_final_inference_report_failure_does_not_interrupt_video(self):
        from pipeworks.embedded.yolo_report import YoloReport

        items = [PipelineContext(frame=object())]
        with patch.object(YoloReport, "_write", side_effect=OSError("report unavailable")):
            self.assertEqual(list(YoloReport().process(iter(items))), items)

    def test_every_n_frames_resumes_and_keeps_interval(self):
        class Child(Step):
            def configure(self, config):
                pass

            def process(self, inputs):
                for item in inputs:
                    seen.append(item.value)
                    if item.value == 2:
                        raise ValueError("invalid result")
                    item.result = True
                    yield item

        seen = []
        child = Child()
        step = EveryNFrames(child, interval_frames=2)
        step._hot_steps = (child,)
        items = [PipelineContext(frame=object(), value=i) for i in range(7)]
        self.assertEqual(list(step.process(iter(items))), items)
        self.assertEqual(seen, [0, 2, 4, 6])
        self.assertTrue(items[4].result)
        self.assertFalse(hasattr(items[2], "result"))

    def test_source_gpu_failure_is_not_retried(self):
        with patch("pipeworks.embedded.rtsp_source.av.open",
                   side_effect=RuntimeError("CUDA error: device lost")) as opened:
            with self.assertRaisesRegex(RuntimeError, "device lost"):
                next(RTSPSource("rtsp://input").process(iter(())))
        opened.assert_called_once()

    def test_async_worker_start_failure_passes_original_and_next_frame_recovers(self):
        from threading import Thread

        class Child(Step):
            def configure(self, config):
                pass

            def process(self, inputs):
                for item in inputs:
                    item.completed = True
                    yield item

        start = Thread.start
        attempts = []

        def start_once(thread):
            if thread.name != "pipeworks-async":
                return start(thread)
            attempts.append(True)
            if len(attempts) == 1:
                raise RuntimeError("worker unavailable")
            return start(thread)

        items = [PipelineContext(value=1), PipelineContext(value=2)]
        with patch("pipeworks.embedded.cuda_async.Thread.start", side_effect=start_once,
                   autospec=True):
            result = list(CudaAsync(Child(), timeout_ms=1000).process(iter(items)))
        self.assertEqual(result, items)
        self.assertFalse(hasattr(items[0], "completed"))
        self.assertTrue(items[1].completed)

    def test_publish_discards_bad_input_then_sends_next_packet(self):
        import test_rtsp_publish as fixtures

        fixture = fixtures.RTSPPublishTests()
        output = fixtures.Output()
        good = fixture.bypass_input(1)
        with patch("pipeworks.embedded.rtsp_publish.av.open", return_value=output):
            list(fixture.publisher(reconnect_interval_ms=0).process(
                iter([PipelineContext(), good])))
        self.assertEqual(len(output.sent), 1)
        self.assertEqual(output.closed, 1)

    def test_encode_discards_bad_input_and_malformed_packet_then_resumes(self):
        import test_nvidia_encode as fixtures

        fixture = fixtures.EncodeTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        encoder = fixtures.Encoder()
        encoder.Encode = lambda frame: [object(), b"valid"]
        fixture.api.CreateEncoder = lambda *args, **kwargs: encoder
        result = list(fixture.step.process(iter([PipelineContext(), fixture.item()])))
        self.assertEqual([bytes(i.packet) for i in result], [b"valid"])
        fixture.stream.synchronize.assert_called()

    def test_async_and_tap_propagate_gpu_error_from_worker(self):
        reached = Event()

        class Fails(Step):
            def configure(self, config):
                pass

            def process(self, inputs):
                for item in inputs:
                    reached.set()
                    raise RuntimeError("CUDA error: device lost")
                    yield item

        for wrapper in (CudaAsync, TapSkipIfBusy):
            with self.subTest(wrapper=wrapper):
                reached.clear()
                step = (wrapper(Fails(), timeout_ms=1000) if wrapper is CudaAsync
                        else wrapper(Fails()))

                def inputs():
                    yield PipelineContext(value=1)
                    self.assertTrue(reached.wait(2))
                    yield PipelineContext(value=2)

                with self.assertRaisesRegex(RuntimeError, "device lost"):
                    list(step.process(inputs()))


if __name__ == "__main__":
    unittest.main()
