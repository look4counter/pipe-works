from contextlib import redirect_stdout
from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from pathlib import Path
from threading import Event, Thread
from tempfile import TemporaryDirectory
import sys
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from pipeworks.embedded.stream_report import report_scope
from pipeworks.models import PipelineContext
import torch


class DetectionProfileTests(unittest.TestCase):
    def test_report_implementations_have_independent_activation_and_profiles(self):
        from pipeworks.embedded import yolo_detect_report as yolo
        from pipeworks.embedded import tensor_rt_report as tensor
        from pipeworks.models import Step

        self.assertEqual(yolo.YoloDetectReport.__bases__, (Step,))
        self.assertEqual(tensor.TensorRTReport.__bases__, (Step,))
        with report_scope():
            self.assertIsNot(yolo.store(), tensor.store())
            yolo.store().activate("YOLO")
            self.assertIsNone(tensor.begin("TensorRT"))
            tensor.store().activate("TensorRT")
            first, second = yolo.begin("YOLO"), tensor.begin("TensorRT")
            with yolo.use(first), tensor.use(second):
                with yolo.span("inference"):
                    pass
                self.assertNotIn("inference", second.parts)
                with tensor.span("postprocess"):
                    pass
                self.assertNotIn("postprocess", first.parts)
            first.finish()
            second.finish("error")
            self.assertEqual(yolo.store().snapshot("YOLO", 0)["states"], {"completed": 1})
            self.assertEqual(tensor.store().snapshot("TensorRT", 0)["states"], {"error": 1})

    def test_reports_only_print_available_measurements(self):
        from collections import Counter
        from pipeworks.embedded import YoloDetectReport, TensorRTReport

        snapshot = {
            "window": {"inference": (2, 3, 4, 3), "total": (6, 3, None, 0)},
            "recent": {"input_wait": (1, 2, None, 0), "other": (0.5, 2, None, 0)},
            "states": Counter(),
            "recent_states": Counter(),
        }
        stats = SimpleNamespace(snapshot=lambda *args: snapshot)
        for report in (YoloDetectReport(), TensorRTReport()):
            with self.subTest(report=type(report).__name__):
                output = StringIO()
                with redirect_stdout(output):
                    report._write(stats, 0)
                text = output.getvalue()
                self.assertNotIn("없음", text)
                self.assertNotIn("배치 큐 대기:", text)
                self.assertIn("모델 실행: CPU 2.00ms(n=3), GPU 4.00ms(n=3)/1s", text)
                self.assertIn("전체: 경과 시간 6.00ms(n=3)/1s", text)
                self.assertIn("입력 동기화: CPU 1.00ms(n=2)/10s", text)
                self.assertIn("기타 실행 비용: 경과 시간 0.50ms(n=2)/10s", text)

    def test_request_parts_are_summed_and_runs_are_isolated(self):
        from pipeworks.embedded.yolo_detect_report import store, Profile

        with report_scope():
            stats = store()
            stats.activate("YOLO")
            profile = Profile("YOLO", stats)
            profile.add("preprocess", 0.002)
            profile.add("preprocess", 0.003)
            profile.finish("completed")
            row = stats.snapshot("YOLO", 0)["recent"]["preprocess"]
            self.assertAlmostEqual(row[0], 5)
            self.assertEqual(row[1], 1)
            with report_scope():
                self.assertEqual(store().snapshot("YOLO", 0)["recent"], {})

    def test_pending_events_are_not_synchronized(self):
        from pipeworks.embedded.tensor_rt_report import store, Profile

        start = SimpleNamespace(elapsed_time=lambda end: 4.0)
        end = SimpleNamespace(query=lambda: False)
        with report_scope():
            stats = store()
            stats.activate("TensorRT")
            profile = Profile("TensorRT", stats)
            profile.add("inference", 0.005, (start, end))
            profile.finish("completed")
            self.assertIsNone(stats.snapshot("TensorRT", 0)["recent"]["inference"][2])
            end.query = lambda: True
            self.assertEqual(stats.snapshot("TensorRT", 0)["recent"]["inference"][2], 4)

    def test_report_preserves_objects_and_flushes_short_run(self):
        from pipeworks.embedded import YoloDetectReport, TensorRTReport
        from pipeworks.embedded.yolo_detect_report import begin as yolo_begin
        from pipeworks.embedded.tensor_rt_report import begin as tensor_rt_begin

        for report, kind in (
            (YoloDetectReport(), "YOLO"),
            (TensorRTReport(), "TensorRT"),
        ):
            item = PipelineContext(value=1)

            def inputs():
                profile = (yolo_begin if kind == "YOLO" else tensor_rt_begin)(kind)
                profile.add("inference", 0.004)
                profile.finish("completed")
                yield item

            output = StringIO()
            with report_scope(), redirect_stdout(output):
                self.assertIs(list(report.process(inputs()))[0], item)
            self.assertIn("완료 1", output.getvalue())
            self.assertIn("모델 실행", output.getvalue())
            self.assertIn("CPU 4.00ms", output.getvalue())

    def test_disabled_measurement_does_not_create_events(self):
        from pipeworks.embedded.yolo_detect_report import begin, span

        with report_scope(), patch("torch.cuda.Event") as event:
            self.assertIsNone(begin("YOLO"))
            with span("inference", SimpleNamespace()):
                pass
            event.assert_not_called()

    def test_recent_window_expires_and_history_is_bounded(self):
        from pipeworks.embedded.yolo_detect_report import DetectionStats, Sample

        stats = DetectionStats()
        with patch("pipeworks.embedded.yolo_detect_report.time.perf_counter", return_value=1):
            for _ in range(10001):
                stats.record("YOLO", {"inference": Sample(0.002)}, "completed")
        self.assertEqual(len(stats.samples["YOLO"]), 10000)
        with patch("pipeworks.embedded.yolo_detect_report.time.perf_counter", return_value=12):
            self.assertEqual(stats.snapshot("YOLO", 11)["recent"], {})
            self.assertEqual(len(stats.states["YOLO"]), 0)

    def test_finish_records_once_and_report_types_do_not_mix(self):
        from pipeworks.embedded.yolo_detect_report import store, Profile

        with report_scope():
            stats = store()
            profile = Profile("YOLO", stats)
            profile.finish()
            profile.finish("error")
            self.assertEqual(stats.snapshot("YOLO", 0)["states"], {"completed": 1})
            self.assertEqual(stats.snapshot("TensorRT", 0)["states"], {})

    def test_reports_print_during_stall_and_stop_on_close(self):
        from pipeworks.embedded import TensorRTReport

        release, printed = Event(), Event()
        report = TensorRTReport()

        def write(*args):
            printed.set()

        def inputs():
            release.wait(3)
            if False:
                yield PipelineContext()

        def run():
            with report_scope():
                list(report.process(inputs()))

        with patch.object(report, "_write", side_effect=write) as output:
            runner = Thread(target=run)
            runner.start()
            try:
                self.assertTrue(printed.wait(2))
            finally:
                release.set()
                runner.join(2)
            self.assertFalse(runner.is_alive())
            count = output.call_count
            time.sleep(0.05)
            self.assertEqual(output.call_count, count)


@unittest.skipUnless(torch.cuda.is_available(), "CUDA가 필요합니다.")
class DetectionCudaTests(unittest.TestCase):
    def frame(self):
        stream = torch.cuda.Stream()
        with torch.cuda.stream(stream):
            frame = torch.full((6, 8), 128, dtype=torch.uint8, device="cuda")
        return PipelineContext(
            frame=frame,
            pixel_format="NV12",
            cuda_stream=stream,
            video_stream=SimpleNamespace(
                codec_context=SimpleNamespace(height=4, width=8)
            ),
        )

    def test_gpu_span_never_adds_synchronization(self):
        from pipeworks.embedded.yolo_detect_report import Profile, span, use

        stream = torch.cuda.Stream()
        profile = Profile("YOLO")
        with (
            patch.object(
                torch.cuda.Stream,
                "synchronize",
                side_effect=AssertionError("추가 동기화"),
            ),
            use(profile),
        ):
            with span("inference", stream), torch.cuda.stream(stream):
                value = torch.ones((10,), device="cuda") * 2
        stream.synchronize()
        sample = profile.parts["inference"]
        sample.resolve()
        self.assertIsNotNone(sample.gpu_ms)

    def test_real_yolo_single_and_batch_have_separate_model_and_nms_times(self):
        from pipeworks.embedded import YoloDetect
        from pipeworks.embedded.yolo_detect_report import store

        path = Path(__file__).resolve().parents[1] / "examples/model/yolo11n.pt"
        if not path.is_file():
            self.skipTest("예제 YOLO 모델이 없습니다.")
        for batch in (False, True):
            with self.subTest(batch=batch), report_scope():
                stats = store()
                stats.activate("YOLO")
                items = [self.frame(), self.frame()]
                results = list(YoloDetect(path, batch=batch).process(iter(items)))
                self.assertEqual(results, items)
                snapshot = stats.snapshot("YOLO", 0)
                for stage in ("preprocess", "inference", "postprocess", "total"):
                    self.assertEqual(snapshot["recent"][stage][1], 2)
                self.assertIsNotNone(snapshot["recent"]["inference"][2])
                self.assertEqual(snapshot["states"]["completed"], 2)
                if batch:
                    self.assertIn("queue", snapshot["recent"])
                    self.assertIn("input_copy", snapshot["recent"])

    def test_real_tensor_rt_pipeline_has_all_stages(self):
        from pipeworks.embedded import TensorRTInference
        from pipeworks.embedded.tensor_rt_report import store, _current

        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))
        from step.tensor_rt_pre_process import TensorRTPreProcess
        from step.tensor_rt_post_process import TensorRTPostProcess

        path = Path(__file__).resolve().parents[1] / "examples/model/yolo11n.plan"
        if not path.is_file():
            self.skipTest("예제 TensorRT 엔진이 없습니다.")
        for batch in (False, True):
            with self.subTest(batch=batch), report_scope():
                stats = store()
                stats.activate("TensorRT")
                item = self.frame()
                pre = TensorRTPreProcess().process(iter([item]))
                infer = TensorRTInference(path, batch=batch).process(pre)
                results = list(TensorRTPostProcess().process(infer))
                self.assertIs(results[0], item)
                self.assertIsNone(_current.get())
                snapshot = stats.snapshot("TensorRT", 0)
                for stage in ("preprocess", "inference", "postprocess", "total"):
                    self.assertEqual(snapshot["recent"][stage][1], 1)
                self.assertIsNotNone(snapshot["recent"]["inference"][2])
                self.assertFalse(hasattr(item, "_tensor_rt_profile"))
                self.assertEqual(snapshot["states"]["completed"], 1)
                if batch:
                    self.assertIn("queue", snapshot["recent"])
                    self.assertIn("input_copy", snapshot["recent"])
                    self.assertIn("output_copy", snapshot["recent"])

    def test_batch_profiles_return_to_their_original_run(self):
        from pipeworks import local_tensor_rt
        from pipeworks.embedded.tensor_rt_report import begin, span, store

        class Session:
            def __init__(self, *args):
                pass

            def infer(self, inputs, stream, context):
                with span("inference", stream):
                    return {"output": inputs * 2}

        with TemporaryDirectory() as directory:
            path = Path(directory) / "model.plan"
            path.write_bytes(b"test")
            path.with_suffix(".yml").write_text(
                "max_batch_size: 2\ntimeout_ms: 1000", encoding="utf-8"
            )

            def run(value):
                with report_scope():
                    stats = store()
                    stats.activate("TensorRT")
                    profile = begin("TensorRT")
                    inputs = torch.full((1, 2), value, device="cuda")
                    result = local_tensor_rt.infer(
                        path, inputs, on_profile_complete=profile.merge
                    )
                    profile.finish()
                    return result, stats.snapshot("TensorRT", 0)

            with (
                patch.object(local_tensor_rt, "_EngineSession", Session),
                ThreadPoolExecutor(2) as pool,
            ):
                results = list(pool.map(run, (1.0, 2.0)))
            for value, (result, snapshot) in zip((1.0, 2.0), results):
                torch.testing.assert_close(
                    result["output"], torch.full((1, 2), value * 2, device="cuda")
                )
                self.assertEqual(snapshot["states"]["completed"], 1)
                self.assertEqual(snapshot["recent"]["inference"][1], 1)
                self.assertEqual(snapshot["recent"]["output_copy"][1], 1)

    def test_tensor_timeout_records_partial_work(self):
        from pipeworks.embedded import CudaAsync
        from pipeworks.embedded.tensor_rt_report import store
        from pipeworks.models import Step

        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))
        from step.tensor_rt_pre_process import TensorRTPreProcess
        from step.tensor_rt_post_process import TensorRTPostProcess

        entered, unblock = Event(), Event()

        class Slow(Step):
            def configure(self, config):
                pass

            def process(self, inputs):
                for item in inputs:
                    item.cuda_stream.synchronize()
                    entered.set()
                    unblock.wait(3)
                    item.model_output = None
                    yield item

        wrapper = CudaAsync(
            TensorRTPreProcess(), Slow(), TensorRTPostProcess(), timeout_ms=200
        )
        with report_scope():
            stats = store()
            stats.activate("TensorRT")
            try:
                list(wrapper.process(iter([self.frame()])))
                self.assertTrue(entered.is_set())
            finally:
                unblock.set()
                self.assertTrue(wrapper._session_lock.acquire(timeout=3))
                wrapper._session_lock.release()
            snapshot = stats.snapshot("TensorRT", 0)
            self.assertEqual(snapshot["states"]["timeout"], 1)
            self.assertEqual(snapshot["states"]["partial"], 1)
            self.assertEqual(snapshot["states"]["completed"], 0)
            self.assertIn("preprocess", snapshot["recent"])


class DetectionAsyncTests(unittest.TestCase):
    def test_busy_and_timeout_are_separate_from_late_completion(self):
        from pipeworks.embedded import CudaAsync, YoloDetect
        from pipeworks.embedded.yolo_detect_report import begin, store
        from pipeworks.execution import release_frame

        entered, unblock = Event(), Event()

        class SlowYolo(YoloDetect):
            def process(self, inputs):
                for item in inputs:
                    profile = begin("YOLO")
                    release_frame()
                    entered.set()
                    unblock.wait(3)
                    profile.finish()
                    yield item

        wrapper = CudaAsync(SlowYolo(Path("model.pt")), timeout_ms=100)
        with report_scope():
            stats = store()
            stats.activate("YOLO")
            items = [PipelineContext(), PipelineContext()]
            try:
                self.assertEqual(list(wrapper.process(iter(items))), items)
                self.assertTrue(entered.is_set())
            finally:
                unblock.set()
                self.assertTrue(wrapper._session_lock.acquire(timeout=3))
                wrapper._session_lock.release()
            states = stats.snapshot("YOLO", 0)["states"]
            self.assertEqual(states, {"completed": 1, "timeout": 1, "busy": 1})

    def test_quick_error_is_not_counted_as_timeout(self):
        from pipeworks.embedded import CudaAsync, YoloDetect
        from pipeworks.embedded.yolo_detect_report import store

        with report_scope():
            stats = store()
            stats.activate("YOLO")
            with self.assertLogs("pipeworks.embedded.cuda_async", level="ERROR"):
                list(
                    CudaAsync(YoloDetect(Path("missing.pt")), timeout_ms=1000).process(
                        iter([PipelineContext()])
                    )
                )
            states = stats.snapshot("YOLO", 0)["states"]
            self.assertEqual(states["error"], 1)
            self.assertEqual(states["timeout"], 0)
