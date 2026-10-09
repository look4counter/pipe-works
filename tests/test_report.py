from contextlib import nullcontext, redirect_stdout
from io import StringIO
from threading import Event, Thread
import time
from types import SimpleNamespace
from unittest.mock import patch
import sys
import unittest

from pipeworks.embedded import StreamReport
from pipeworks.embedded import stream_report as report
from pipeworks.embedded.nvidia_decode import NvidiaDecode
from pipeworks.embedded.nvidia_encode import NvidiaEncode
from pipeworks.models import PipelineContext


class ReportTests(unittest.TestCase):
    def test_receive_and_publish_status_transitions(self):
        self.assertEqual(report._connection_status(0), ("대기", "대기"))
        with patch.object(report.time, "perf_counter", return_value=1.0):
            report.record_receive(True)
            report.record_publish(True)
        self.assertEqual(report._connection_status(2.0), ("성공", "성공"))
        with patch.object(report.time, "perf_counter", return_value=3.0):
            report.record_publish(False)
        self.assertEqual(report._connection_status(4.0), ("성공", "실패"))
        self.assertEqual(report._connection_status(7.0), ("중단", "실패"))

    def test_terminal_report_prints_while_upstream_has_no_outputs(self):
        release = Event()
        output = StringIO()

        def silent_upstream():
            release.wait(4)
            if False:
                yield PipelineContext()

        def consume():
            with redirect_stdout(output), report.report_scope():
                list(StreamReport().process(silent_upstream()))

        runner = Thread(target=consume)
        runner.start()
        try:
            deadline = time.monotonic() + 3
            while "수신 대기" not in output.getvalue() and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertIn("수신 대기", output.getvalue())
            self.assertIn("송신 대기", output.getvalue())
            self.assertIn("FPS 0.0", output.getvalue())
        finally:
            release.set()
            runner.join(timeout=3)
        self.assertFalse(runner.is_alive())
        previous = output.getvalue()
        time.sleep(1.1)
        self.assertEqual(output.getvalue(), previous)

    def test_terminal_report_includes_frame_and_inference_averages(self):
        release = Event()
        output = StringIO()

        def silent_upstream():
            release.wait(3)
            if False:
                yield PipelineContext()

        def consume():
            with redirect_stdout(output), report.report_scope():
                report.record_frame(0.02)
                report.record_inference(0.005)
                report.record_stage("encode", 0.01)
                list(StreamReport().process(silent_upstream()))

        runner = Thread(target=consume)
        runner.start()
        try:
            deadline = time.monotonic() + 3
            while "추론 5.0ms/1s" not in output.getvalue() and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertIn("프레임처리 20.0ms/1s, 20.0ms/10s", output.getvalue())
            self.assertIn("추론 5.0ms/1s, 5.0ms/10s (1건)", output.getvalue())
            self.assertIn("인코딩 10.0ms", output.getvalue())
            self.assertEqual(output.getvalue().count("\n"), 2)
        finally:
            release.set()
            runner.join(timeout=3)
        self.assertFalse(runner.is_alive())

    def test_stream_report_passes_same_packet_context(self):
        packet = PipelineContext(packet=object())
        result = list(StreamReport().process(iter((packet,))))
        self.assertEqual(result, [packet])
        self.assertIs(result[0], packet)

    def setUp(self):
        report._default_stats = report._ReportStats()

    def test_overlapping_run_scopes_keep_metrics_separate(self):
        from contextvars import copy_context
        from threading import Thread

        with report.report_scope():
            first = copy_context()
        with report.report_scope():
            second = copy_context()

        first.run(report.record_frame, 0.01)
        first.run(report.record_stage, "encode", 0.01)
        second.run(report.record_frame, 0.09)
        second.run(report.record_inference, 0.02)
        second.run(report.record_stage, "encode", 0.09)
        worker = Thread(target=first.run, args=(report.record_inference, 0.015))
        worker.start()
        worker.join()

        first_stats = first.run(report._stats)
        second_stats = second.run(report._stats)
        first_stats.window_started_at = 0.0
        second_stats.window_started_at = 0.0
        with patch.object(report.time, "perf_counter", return_value=1.0):
            first_result = first.run(report._take_report)
            second_result = second.run(report._take_report)
        self.assertEqual(first_result[2], 1)
        self.assertAlmostEqual(first_result[3], 15.0)
        self.assertAlmostEqual(first_result[1], 10.0)
        self.assertEqual(second_result[2], 1)
        self.assertAlmostEqual(second_result[3], 20.0)
        self.assertAlmostEqual(second_result[1], 90.0)
        self.assertAlmostEqual(first.run(report._take_stage_report)["encode"], 10.0)
        self.assertAlmostEqual(second.run(report._take_stage_report)["encode"], 90.0)

    def test_stage_timing_averages_only_recorded_work(self):
        report.record_stage("batch_queue", 0.02)
        report.record_stage("batch_queue", 0.04)
        report.record_stage("encode", 0.01)
        stages = report._take_stage_report()
        self.assertAlmostEqual(stages["batch_queue"], 30.0)
        self.assertAlmostEqual(stages["encode"], 10.0)
        self.assertNotIn("publish", stages)
        self.assertEqual(report._take_stage_report(), {})


    def test_fps_and_average_processing_time(self):
        with patch.object(report.time, "perf_counter", side_effect=[10.0, 10.1, 11.0]):
            report.record_frame(0.01)
            report.record_frame(0.02)
            fps, average_ms, inference_count, average_inference_ms, _, _ = report._take_report()
        self.assertAlmostEqual(fps, 2.0)
        self.assertAlmostEqual(average_ms, 15.0)
        self.assertEqual(inference_count, 0)
        self.assertIsNone(average_inference_ms)

    def test_recent_ten_seconds_weights_samples_and_expires_boundary(self):
        with report.report_scope():
            with patch.object(report.time, "perf_counter", return_value=0):
                report.record_frame(.01)
                report.record_inference(.02)
            with patch.object(report.time, "perf_counter", return_value=1):
                first = report._take_report()
            with patch.object(report.time, "perf_counter", return_value=2):
                for _ in range(3):
                    report.record_frame(.03)
                report.record_inference(.06)
            with patch.object(report.time, "perf_counter", return_value=3):
                second = report._take_report()
            self.assertAlmostEqual(first[4], 10)
            self.assertAlmostEqual(second[1], 30)
            self.assertAlmostEqual(second[4], 25)
            self.assertAlmostEqual(second[5], 40)
            with patch.object(report.time, "perf_counter", return_value=10):
                boundary = report._take_report()
            self.assertEqual(boundary[2], 0)
            self.assertIsNone(boundary[3])
            self.assertAlmostEqual(boundary[4], 30)
            self.assertAlmostEqual(boundary[5], 60)
            with patch.object(report.time, "perf_counter", return_value=12):
                empty = report._take_report()
            self.assertIsNone(empty[4])
            self.assertIsNone(empty[5])

    def test_inference_count_and_average_reset_each_interval(self):
        with patch.object(report.time, "perf_counter", side_effect=[10.0, 10.1, 11.0, 12.0]):
            report.record_inference(0.01)
            report.record_inference(0.02)
            first = report._take_report()
            second = report._take_report()
        self.assertEqual(first[2], 2)
        self.assertAlmostEqual(first[3], 15.0)
        self.assertEqual(second[2], 0)
        self.assertIsNone(second[3])






    def test_decode_stamps_frame(self):
        frame = object()
        decoder = SimpleNamespace(
            GetPixelFormat=lambda: "NV12",
            Decode=lambda packet: [frame],
            Flush=lambda: [],
        )
        codec = SimpleNamespace(name="h264")
        stream = SimpleNamespace(codec=codec)
        class Packet:
            pts = 1

            def __bytes__(self):
                return b"data"

        nvc = SimpleNamespace(
            cudaVideoCodec=SimpleNamespace(H264=1, HEVC=2),
            OutputColorType=SimpleNamespace(NATIVE=1),
            DisplayDecodeLatencyType=SimpleNamespace(NATIVE=1),
            PacketData=lambda: SimpleNamespace(),
            CreateDecoder=lambda **kwargs: decoder,
        )
        step = NvidiaDecode()
        step.configure(SimpleNamespace())
        with patch.dict(sys.modules, {"PyNvVideoCodec": nvc}), \
             patch("pipeworks.embedded.nvidia_decode.torch.cuda.Stream", return_value=SimpleNamespace(cuda_stream=0)), \
             patch("pipeworks.embedded.nvidia_decode.torch.cuda.stream", return_value=nullcontext()), \
             patch("pipeworks.embedded.nvidia_decode.time.perf_counter", return_value=10.0):
            output = list(step.process(iter((PipelineContext(packet=Packet(), video_stream=stream),))))
        self.assertEqual(len(output), 1)
        self.assertIs(output[0].frame, frame)
        self.assertEqual(output[0].processing_started_at, 10.0)

    def test_encode_records_each_frame_and_accepts_missing_start(self):
        encoder = SimpleNamespace(Encode=lambda frame: b"data", EndEncode=lambda: [])
        nvc = SimpleNamespace(CreateEncoder=lambda *args, **kwargs: encoder)
        codec = SimpleNamespace(name="h264", width=4, height=4)
        stream = SimpleNamespace(codec_context=codec)
        frame = PipelineContext(
            frame=object(), video_stream=stream, cuda_stream=SimpleNamespace(cuda_stream=0),
            pixel_format="NV12", processing_started_at=100.0,
        )
        without_start = PipelineContext(
            frame=object(), video_stream=stream, cuda_stream=SimpleNamespace(cuda_stream=0), pixel_format="NV12",
        )
        step = NvidiaEncode()
        step.configure(SimpleNamespace())
        with patch.dict(sys.modules, {"PyNvVideoCodec": nvc}), \
             patch("pipeworks.embedded.nvidia_encode.torch.cuda.stream", return_value=nullcontext()), \
             patch("pipeworks.embedded.nvidia_encode.time.perf_counter", return_value=100.02), \
             patch("pipeworks.embedded.nvidia_encode.record_frame") as record:
            output = list(step.process(iter((frame, without_start))))
        self.assertEqual(len(output), 2)
        record.assert_called_once()
        self.assertAlmostEqual(record.call_args.args[0], 0.02)


if __name__ == "__main__":
    unittest.main()
