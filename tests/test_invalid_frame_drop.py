import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "examples")]

from pipeworks.embedded import CudaAsync, EveryNFrames
from pipeworks.models import PipelineContext, Step
from step.box_overlay import BoxOverlay
from step.yolo_pre_process import YoloPreProcess


@unittest.skipUnless(torch.cuda.is_available(), "CUDA가 필요합니다.")
class InvalidFrameDropTests(unittest.TestCase):
    def frame(self, height=4, width=8, shape=(6, 8)):
        stream = torch.cuda.Stream()
        with torch.cuda.stream(stream):
            frame = torch.full(shape, 128, dtype=torch.uint8, device="cuda")
        stream.synchronize()
        return PipelineContext(
            frame=frame,
            pixel_format="NV12",
            cuda_stream=stream,
            video_stream=SimpleNamespace(
                codec_context=SimpleNamespace(height=height, width=width)
            ),
        )

    def test_invalid_dimensions_drop_and_resume_without_mutating_input(self):
        for factory in (YoloPreProcess, BoxOverlay):
            for height, width in ((3, 8), (4, 7), (0, 8), (-2, 8),
                                  (None, 8), (True, 8), (4, 8.5)):
                with self.subTest(step=factory.__name__, height=height, width=width):
                    first, bad, last = self.frame(), self.frame(height, width), self.frame()
                    original = bad.frame.clone()
                    pointer = bad.frame.data_ptr()
                    with self.assertLogs(level="WARNING"):
                        result = list(factory().process(iter((first, bad, last))))
                    self.assertEqual(result, [first, last])
                    self.assertEqual(bad.frame.data_ptr(), pointer)
                    torch.testing.assert_close(bad.frame, original)
                    self.assertEqual(bad.video_stream.codec_context.height, height)
                    self.assertEqual(bad.video_stream.codec_context.width, width)

    def test_short_nv12_buffer_is_dropped(self):
        for factory in (YoloPreProcess, BoxOverlay):
            for shape in ((5, 8), (6, 7), (47,)):
                with self.subTest(step=factory.__name__, shape=shape):
                    bad, good = self.frame(shape=shape), self.frame()
                    with self.assertLogs(level="WARNING"):
                        self.assertEqual(list(factory().process(iter((bad, good)))), [good])

    def test_all_invalid_and_empty_inputs_finish(self):
        for factory in (YoloPreProcess, BoxOverlay):
            step = factory()
            self.assertEqual(list(step.process(iter(()))), [])
            with self.assertLogs(level="WARNING"):
                self.assertEqual(list(step.process(iter((self.frame(3), self.frame(5))))), [])

    def test_preprocess_finishes_profile_and_does_not_submit_gpu_work(self):
        bad = self.frame(3)
        profile = Mock()
        with (
            patch("step.yolo_pre_process.begin_preprocess", return_value=profile),
            patch.object(torch.cuda, "Event", side_effect=AssertionError("새 GPU 작업")),
            self.assertLogs(level="WARNING"),
        ):
            self.assertEqual(list(YoloPreProcess().process(iter((bad,)))), [])
        profile.finish.assert_called_once_with("error")
        self.assertNotIn("_inference_profile", vars(bad))

    def test_unrelated_errors_still_raise(self):
        for factory in (YoloPreProcess, BoxOverlay):
            bad = self.frame()
            bad.pixel_format = "P016"
            with self.subTest(step=factory.__name__), self.assertRaises(ValueError):
                list(factory().process(iter((bad,))))
        bad = self.frame()
        bad.frame = bad.frame.float()
        with self.assertRaises(ValueError):
            list(YoloPreProcess().process(iter((bad,))))
        with self.assertRaises(ValueError):
            YoloPreProcess(size=(0, 8))
        with self.assertRaises(ValueError):
            BoxOverlay().configure(SimpleNamespace(line_width=0))

    def test_drop_survives_wrappers_and_skips_following_stage(self):
        class Observe(Step):
            def __init__(self, seen):
                self.seen = seen

            def configure(self, config):
                pass

            def process(self, inputs):
                for item in inputs:
                    self.seen.append(item.video_stream.codec_context.height)
                    yield item

        for wrap in ("async", "async_single", "every", "every_async"):
            for factory in (YoloPreProcess, BoxOverlay):
                with self.subTest(wrap=wrap, step=factory.__name__):
                    seen = []
                    if wrap == "every":
                        step = EveryNFrames(factory(), Observe(seen))
                    else:
                        steps = (factory(),) if wrap == "async_single" else (factory(), Observe(seen))
                        step = CudaAsync(*steps, timeout_ms=10000)
                        if wrap == "every_async":
                            step = EveryNFrames(step)
                    first, bad, bad_again, last = (
                        self.frame(), self.frame(3), self.frame(5), self.frame()
                    )
                    # 디코더 대여 버퍼의 정리 경로에서도 폐기 타입이 유지되어야 한다.
                    bad._decode_buffer = object()
                    with self.assertLogs(level="WARNING"):
                        result = list(step.process(iter((first, bad, bad_again, last))))
                    self.assertEqual(result, [first, last])
                    self.assertEqual(seen, [] if wrap == "async_single" else [4, 4])


if __name__ == "__main__":
    unittest.main()
