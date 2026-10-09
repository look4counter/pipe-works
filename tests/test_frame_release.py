from contextvars import copy_context
from pathlib import Path
from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import torch

from pipeworks.embedded import CudaAsync, YoloDetect
from pipeworks.models import PipelineContext, Step


class FrameReleaseTests(unittest.TestCase):
    def test_timeout_release_event_matrix_without_clones(self):
        from pipeworks.execution import release_frame

        class BrokenEvent:
            def query(self):
                raise RuntimeError("query failed")

        for ready, expected in ((None, True), (SimpleNamespace(query=lambda: True), True),
                                (SimpleNamespace(query=lambda: False), False), (BrokenEvent(), False)):
            with self.subTest(ready=ready):
                entered, unblock, cleaned = Event(), Event(), Event()
                self.addCleanup(unblock.set)

                class Slow(Step):
                    def process(self, inputs):
                        try:
                            for item in inputs:
                                release_frame(ready_event=ready)
                                entered.set()
                                unblock.wait(5)
                                item.late = True
                                yield item
                        finally:
                            cleaned.set()

                original = PipelineContext(frame=torch.tensor([1]))
                following = PipelineContext(frame=torch.tensor([2]))
                frame = original.frame
                with patch.object(torch.Tensor, "clone", side_effect=AssertionError("input clone")):
                    if isinstance(ready, BrokenEvent):
                        with self.assertLogs("pipeworks.embedded.cuda_async", level="ERROR"):
                            result = list(CudaAsync(Slow(), timeout_ms=100).process(iter([original, following])))
                    else:
                        result = list(CudaAsync(Slow(), timeout_ms=100).process(iter([original, following])))
                self.assertTrue(entered.is_set())
                self.assertEqual(result, [original, following] if expected else [following])
                self.assertIs(original.frame, frame)
                self.assertFalse(hasattr(original, "late"))
                unblock.set()
                self.assertTrue(cleaned.wait(2))
                self.assertFalse(hasattr(original, "late"))

    def test_multiple_steps_accept_frame_release_but_not_input_release(self):
        from pipeworks.execution import release_frame, release_input

        for signal, expected in ((release_frame, True), (release_input, False)):
            with self.subTest(signal=signal.__name__):
                unblock, entered = Event(), Event()
                self.addCleanup(unblock.set)

                class Pre(Step):
                    def process(self, inputs):
                        for item in inputs:
                            signal()
                            item.model_input = torch.tensor([3])
                            yield item

                class Infer(Step):
                    def process(self, inputs):
                        for item in inputs:
                            entered.set()
                            unblock.wait(5)
                            item.result = 7
                            yield item

                original = PipelineContext(frame=torch.tensor([1]))
                wrapper = CudaAsync(Pre(), Infer(), timeout_ms=100)
                self.assertEqual(list(wrapper.process(iter([original]))), [original] if expected else [])
                self.assertTrue(entered.is_set())
                self.assertFalse(hasattr(original, "model_input"))
                unblock.set()
                self.assertTrue(wrapper._session_lock.acquire(timeout=2))
                wrapper._session_lock.release()

    def test_stale_frame_release_context_cannot_release_next_request(self):
        from pipeworks.execution import release_frame
        unblock = Event()
        self.addCleanup(unblock.set)

        class Stale(Step):
            def process(self, inputs):
                for index, item in enumerate(inputs):
                    if index == 0:
                        saved = copy_context()
                    else:
                        saved.run(release_frame)
                        unblock.wait(5)
                    yield item

        first, second = PipelineContext(frame=torch.tensor([1])), PipelineContext(frame=torch.tensor([2]))
        wrapper = CudaAsync(Stale(), timeout_ms=100)
        self.assertEqual(list(wrapper.process(iter([first, second]))), [first])
        unblock.set()
        self.assertTrue(wrapper._session_lock.acquire(timeout=2))
        wrapper._session_lock.release()

    def test_frame_release_outside_request_is_noop(self):
        from pipeworks.execution import release_frame
        self.assertIsNone(release_frame())

    @unittest.skipUnless(torch.cuda.is_available(), "CUDA required")
    def test_failed_cuda_cleanup_drops_unreleased_original(self):
        class NoRelease(Step):
            def process(self, inputs):
                yield from inputs

        stream = torch.cuda.Stream()
        original = PipelineContext(cuda_stream=stream)
        wrapper = CudaAsync(NoRelease(), timeout_ms=1000)
        with patch.object(torch.cuda.Stream, "synchronize", side_effect=RuntimeError("CUDA cleanup failed")), self.assertLogs(
            "pipeworks.embedded.cuda_async", level="ERROR"
        ):
            self.assertEqual(list(wrapper.process(iter([original]))), [])
            self.assertTrue(wrapper._session_lock.acquire(timeout=2))
            wrapper._session_lock.release()

    @unittest.skipUnless(torch.cuda.is_available(), "CUDA required")
    def test_yolo_single_and_batch_release_rgb_before_inference_wait(self):
        from pipeworks.local_yolo import _nv12_to_rgb
        from ultralytics.engine.results import Results

        for batch in (False, True):
            with self.subTest(batch=batch):
                stream = torch.cuda.Stream()
                with torch.cuda.stream(stream):
                    frame = torch.full((6, 4), 128, dtype=torch.uint8, device="cuda")
                    expected = _nv12_to_rgb(frame)
                stream.synchronize()
                item = PipelineContext(frame=frame, cuda_stream=stream, pixel_format="NV12",
                                       video_stream=SimpleNamespace(codec_context=SimpleNamespace(height=4, width=4)))
                entered, unblock = Event(), Event()
                self.addCleanup(unblock.set)
                observed = []

                def predict(images, **kwargs):
                    prepared = torch.cuda.Event()
                    prepared.record(torch.cuda.current_stream())
                    prepared.synchronize()
                    observed.append(images)
                    entered.set()
                    unblock.wait(5)
                    return [Results(images[0].permute(1, 2, 0), path="test", names={},
                                    boxes=torch.empty((0, 6), device="cuda"))]

                def infer(path, rgb, *args, ready_event, **kwargs):
                    ready_event.synchronize()
                    observed.append(rgb)
                    entered.set()
                    unblock.wait(5)
                    self.assertTrue(torch.equal(rgb, expected))
                    return None

                model = Mock()
                model.predict.side_effect = predict
                wrapper = CudaAsync(YoloDetect(Path("model.pt"), batch=batch), timeout_ms=500)
                with patch("ultralytics.YOLO", return_value=model), patch(
                    "pipeworks.embedded.yolo_detect.infer", side_effect=infer
                ):
                    try:
                        self.assertEqual(list(wrapper.process(iter([item]))), [item])
                        self.assertTrue(entered.is_set())
                        self.assertIs(item.frame, frame)
                        model_input_before = observed[0].clone()
                        with torch.cuda.stream(stream):
                            frame.fill_(7)
                        stream.synchronize()
                        self.assertTrue(torch.equal(observed[0], model_input_before))
                        if batch:
                            self.assertEqual(observed[0].shape, (3, 4, 4))
                            self.assertEqual(observed[0].dtype, torch.float32)
                            self.assertTrue(torch.equal(observed[0], expected))
                    finally:
                        unblock.set()
                        self.assertTrue(wrapper._session_lock.acquire(timeout=3))
                        wrapper._session_lock.release()
