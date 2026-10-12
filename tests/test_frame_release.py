from contextvars import copy_context
from pathlib import Path
from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import torch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))
from pipeworks import Backend
from pipeworks.embedded import CudaAsync, YoloInference
from pipeworks.models import PipelineContext, Step


class FrameReleaseTests(unittest.TestCase):
    def test_timeout_release_event_matrix_without_clones(self):
        from pipeworks.execution import release_frame

        class BrokenEvent:
            def query(self):
                raise RuntimeError("query failed")

        for ready, expected in (
            (None, True),
            (SimpleNamespace(query=lambda: True), True),
            (SimpleNamespace(query=lambda: False), False),
            (BrokenEvent(), False),
        ):
            with self.subTest(ready=ready):
                entered, unblock, cleaned = Event(), Event(), Event()
                self.addCleanup(unblock.set)

                class Slow(Step):
                    def configure(self, config):
                        pass

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
                with patch.object(
                    torch.Tensor, "clone", side_effect=AssertionError("input clone")
                ):
                    if isinstance(ready, BrokenEvent):
                        with self.assertLogs(
                            "pipeworks.embedded.cuda_async", level="ERROR"
                        ):
                            result = list(
                                CudaAsync(Slow(), timeout_ms=100).process(
                                    iter([original, following])
                                )
                            )
                    else:
                        result = list(
                            CudaAsync(Slow(), timeout_ms=100).process(
                                iter([original, following])
                            )
                        )
                self.assertTrue(entered.is_set())
                self.assertEqual(
                    result, [original, following] if expected else [following]
                )
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
                    def configure(self, config):
                        pass

                    def process(self, inputs):
                        for item in inputs:
                            signal()
                            item.model_input = torch.tensor([3])
                            yield item

                class Infer(Step):
                    def configure(self, config):
                        pass

                    def process(self, inputs):
                        for item in inputs:
                            entered.set()
                            unblock.wait(5)
                            item.result = 7
                            yield item

                original = PipelineContext(frame=torch.tensor([1]))
                wrapper = CudaAsync(Pre(), Infer(), timeout_ms=100)
                self.assertEqual(
                    list(wrapper.process(iter([original]))),
                    [original] if expected else [],
                )
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
            def configure(self, config):
                pass

            def process(self, inputs):
                for index, item in enumerate(inputs):
                    if index == 0:
                        saved = copy_context()
                    else:
                        saved.run(release_frame)
                        unblock.wait(5)
                    yield item

        first, second = (
            PipelineContext(frame=torch.tensor([1])),
            PipelineContext(frame=torch.tensor([2])),
        )
        wrapper = CudaAsync(Stale(), timeout_ms=100)
        self.assertEqual(list(wrapper.process(iter([first, second]))), [first])
        unblock.set()
        self.assertTrue(wrapper._session_lock.acquire(timeout=2))
        wrapper._session_lock.release()

    def test_frame_release_outside_request_is_noop(self):
        from pipeworks.execution import release_frame

        self.assertIsNone(release_frame())

    @unittest.skipUnless(torch.cuda.is_available(), "CUDA required")
    def test_preprocess_releases_frame_before_single_or_batch_inference_wait(self):
        from step.yolo_pre_process import YoloPreProcess, nv12_to_rgb

        for batch in (False, True):
            with self.subTest(batch=batch):
                stream = torch.cuda.Stream()
                with torch.cuda.stream(stream):
                    frame = torch.full((6, 4), 128, dtype=torch.uint8, device="cuda")
                    expected = nv12_to_rgb(frame).unsqueeze(0)
                stream.synchronize()
                item = PipelineContext(
                    frame=frame, cuda_stream=stream, pixel_format="NV12",
                    video_stream=SimpleNamespace(codec_context=SimpleNamespace(height=4, width=4)),
                )
                entered, unblock = Event(), Event()
                observed = []

                def slow(inputs, *args, ready_event=None, **kwargs):
                    if not isinstance(inputs, torch.Tensor):
                        inputs = args[0]
                    if ready_event is not None:
                        ready_event.synchronize()
                    torch.cuda.current_stream().synchronize()
                    observed.append(inputs)
                    entered.set()
                    unblock.wait(5)
                    callback = kwargs.get("on_inference_complete")
                    if callback is not None:
                        callback(0.001)
                    return {"output0": inputs.neg()}

                wrapper = CudaAsync(
                    YoloPreProcess(size=(4, 4)),
                    YoloInference("model.pt", backend=Backend.ULTRALYTICS, batch=batch),
                    timeout_ms=500,
                )
                with (
                    patch("pipeworks.embedded.yolo_inference._Session", return_value=SimpleNamespace(infer=slow)),
                    patch("pipeworks.local_yolo_inference.infer", side_effect=slow),
                ):
                    try:
                        self.assertEqual(list(wrapper.process(iter([item]))), [item])
                        self.assertTrue(entered.is_set())
                        self.assertIs(item.frame, frame)
                        before = observed[0].clone()
                        torch.testing.assert_close(before, expected)
                        with torch.cuda.stream(stream):
                            frame.fill_(7)
                        stream.synchronize()
                        torch.testing.assert_close(observed[0], before)
                        self.assertFalse(hasattr(item, "model_input"))
                    finally:
                        unblock.set()
                        self.assertTrue(wrapper._session_lock.acquire(timeout=3))
                        wrapper._session_lock.release()

    @unittest.skipUnless(torch.cuda.is_available(), "CUDA required")
    def test_failed_cuda_cleanup_drops_unreleased_original(self):
        class NoRelease(Step):
            def configure(self, config):
                pass

            def process(self, inputs):
                yield from inputs

        stream = torch.cuda.Stream()
        original = PipelineContext(cuda_stream=stream)
        wrapper = CudaAsync(NoRelease(), timeout_ms=1000)
        with (
            patch.object(torch.cuda.Stream, "synchronize", side_effect=RuntimeError("CUDA cleanup failed")),
            self.assertLogs("pipeworks.embedded.cuda_async", level="ERROR"),
        ):
            self.assertEqual(list(wrapper.process(iter([original]))), [])
            self.assertTrue(wrapper._session_lock.acquire(timeout=2))
            wrapper._session_lock.release()
