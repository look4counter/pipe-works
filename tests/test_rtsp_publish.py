import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from fractions import Fraction
from io import BytesIO
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pipeworks.embedded.rtsp_publish import RTSPPublish
from pipeworks.models import PipelineContext
from pipeworks.video import CodecInfo, VideoStreamInfo
from dataclasses import replace
import av
from av import open as open_container


class Output:
    def __init__(self, fail_mux=False):
        self._container = open_container(BytesIO(), mode="w", format="matroska")
        self.stream = self._container.add_stream("h264")
        self.stream.time_base = Fraction(1, 90000)
        self.sent = []
        self.closed = 0
        self.fail_mux = fail_mux

    def add_stream_from_template(self, template, **kwargs):
        return self.stream

    def start_encoding(self):
        pass

    def mux(self, packet):
        if self.fail_mux:
            raise OSError("mux failed")
        self.sent.append(packet)

    def close(self):
        self.closed += 1


class RTSPPublishTests(unittest.TestCase):
    def test_reconnect_interval_ms_retry_boundary(self):
        for failure in ["open", "mux"]:
            with self.subTest(failure=failure):
                failed = Output(fail_mux=True)
                recovered = Output()
                initial = OSError("open failed") if failure == "open" else failed
                publisher = self.publisher(reconnect_interval_ms=250)
                with (
                    patch(
                        "pipeworks.embedded.rtsp_publish.av.open",
                        side_effect=[initial, recovered],
                    ) as opened,
                    patch(
                        "pipeworks.embedded.rtsp_publish.time.monotonic",
                        side_effect=[0, 0, 0.249, 0.25],
                    ),
                ):
                    list(publisher.process(iter([self.bypass_input(0)] * 3)))
                self.assertEqual(opened.call_count, 2)
                self.assertEqual(len(recovered.sent), 1)
        self.assertEqual(self.publisher().reconnect_interval_ms, 3000)

    def test_invalid_reconnect_interval_configuration(self):
        configs = [
            {"reconnect_interval_ms": value}
            for value in [-1, True, "3000", None, float("nan"), float("inf")]
        ]
        for config in configs:
            with (
                self.subTest(config=config),
                self.assertRaisesRegex(ValueError, "reconnect_interval_ms"),
            ):
                self.publisher(**config)

    def test_current_options_ignore_unused_legacy_keys(self):
        for config, interval_ms, timeout_ms in [
            ({"reconnect_interval": 99, "timeout": 99}, 3000, 5000),
            (
                {
                    "reconnect_interval": 99,
                    "timeout": 99,
                    "reconnect_interval_ms": 250,
                    "timeout_ms": 1250.5,
                },
                250,
                1250.5,
            ),
        ]:
            with self.subTest(config=config):
                step = RTSPPublish("rtsp://output")
                step.configure(SimpleNamespace(**config))
                self.assertEqual(step.reconnect_interval_ms, interval_ms)
                self.assertEqual(step.timeout_ms, timeout_ms)

    def test_timeout_ms_conversion(self):
        for config, microseconds in [
            ({}, "5000000"),
            ({"timeout_ms": 0}, "0"),
            ({"timeout_ms": 250}, "250000"),
            ({"timeout_ms": 1250.5}, "1250500"),
        ]:
            with self.subTest(config=config):
                publisher = self.publisher(**config)
                with patch(
                    "pipeworks.embedded.rtsp_publish.av.open", return_value=Output()
                ) as opened:
                    list(publisher.process(iter([self.bypass_input(0)])))
                self.assertEqual(
                    opened.call_args.kwargs["options"]["timeout"], microseconds
                )
                self.assertEqual(publisher.timeout_ms, config.get("timeout_ms", 5000))

    def test_invalid_timeout_configuration(self):
        configs = [
            {"timeout_ms": value}
            for value in [-1, True, "5000", None, float("nan"), float("inf")]
        ]
        for config in configs:
            with (
                self.subTest(config=config),
                self.assertRaisesRegex(ValueError, "timeout_ms"),
            ):
                self.publisher(**config)

    def publisher(self, **config):
        publisher = RTSPPublish("rtsp://output")
        publisher.configure(SimpleNamespace(**config))
        return publisher

    def bypass_input(self, dts, pts=None):
        stream = VideoStreamInfo(
            CodecInfo("h264", 640, 480),
            time_base=Fraction(1, 90000),
        )
        packet = av.Packet(b"data")
        packet.dts, packet.pts = dts, pts
        packet.duration = 3000
        packet.time_base = Fraction(1, 90000)
        return PipelineContext(packet=packet, video_stream=stream)

    def test_bypass_repairs_dts_and_consumes_input(self):
        output = Output()
        first = self.bypass_input(3000, 3000)
        second = self.bypass_input(3000, 3000)
        second.video_stream = first.video_stream
        with (
            patch("pipeworks.embedded.rtsp_publish.av.open", return_value=output),
            patch("pipeworks.embedded.rtsp_publish.record_publish") as status,
        ):
            result = list(self.publisher().process(iter([first, second])))
        self.assertEqual([call.args[0] for call in status.call_args_list], [True, True])
        self.assertEqual(result, [])
        self.assertEqual(len(output.sent), 2)
        self.assertEqual(output.sent[1].dts, 6000)
        self.assertEqual(output.sent[1].pts, 6000)
        self.assertEqual(second.packet.dts, 3000)
        self.assertEqual(second.packet.pts, 3000)
        self.assertIsNone(second.packet.stream)
        self.assertEqual(output.closed, 1)

    def test_bypass_fills_missing_dts(self):
        output = Output()
        first = self.bypass_input(0)
        second = self.bypass_input(None)
        second.video_stream = first.video_stream
        with patch("pipeworks.embedded.rtsp_publish.av.open", return_value=output):
            list(self.publisher().process(iter([first, second])))
        self.assertEqual(output.sent[1].dts, 3000)
        self.assertIsNone(second.packet.dts)

    def test_output_options_follow_configuration(self):
        output = Output()
        publisher = self.publisher(transport="udp", timeout_ms=10000, packet_size=1200)
        with patch(
            "pipeworks.embedded.rtsp_publish.av.open", return_value=output
        ) as open_mock:
            list(publisher.process(iter([self.bypass_input(0)])))
        self.assertEqual(
            open_mock.call_args.kwargs["options"],
            {
                "rtsp_transport": "udp",
                "pkt_size": "1200",
                "timeout": "10000000",
            },
        )

    def test_encoder_shape_uses_packet_path(self):
        output = Output()
        context = self.bypass_input(3000, 3000)
        encoded = PipelineContext(
            packet=context.packet, video_stream=context.video_stream
        )
        with patch("pipeworks.embedded.rtsp_publish.av.open", return_value=output):
            result = list(self.publisher().process(iter([encoded])))
        self.assertEqual(result, [])
        self.assertEqual([bytes(packet) for packet in output.sent], [bytes(context.packet)])
        self.assertIsNot(output.sent[0], context.packet)
        self.assertEqual(output.closed, 1)

    def test_mux_failure_retries_or_raises_by_setting(self):
        failed = Output(fail_mux=True)
        recovered = Output()
        with (
            patch(
                "pipeworks.embedded.rtsp_publish.av.open",
                side_effect=[failed, recovered],
            ),
            patch(
                "pipeworks.embedded.rtsp_publish.time.monotonic",
                side_effect=[0, 0, 1, 2],
            ),
            patch("pipeworks.embedded.rtsp_publish.record_publish") as status,
        ):
            result = list(
                self.publisher(reconnect_interval_ms=1000).process(
                    iter([self.bypass_input(0)] * 3)
                )
            )
        self.assertEqual(
            [call.args[0] for call in status.call_args_list], [False, True, True]
        )
        self.assertEqual(result, [])
        self.assertEqual(failed.closed, 1)
        self.assertEqual(len(recovered.sent), 2)
        self.assertEqual(recovered.closed, 1)

        failed = Output(fail_mux=True)
        with patch("pipeworks.embedded.rtsp_publish.av.open", return_value=failed):
            self.assertEqual(list(
                self.publisher(reconnect=False).process(iter([self.bypass_input(0)]))
            ), [])
        self.assertEqual(failed.closed, 1)

    def test_stream_configuration_change_reopens_output(self):
        first_output = Output()
        second_output = Output()
        first = self.bypass_input(0)
        second = self.bypass_input(0)
        second.video_stream = replace(second.video_stream,
                                      codec_context=CodecInfo("h264", 1280, 480))
        with patch(
            "pipeworks.embedded.rtsp_publish.av.open",
            side_effect=[first_output, second_output],
        ):
            list(self.publisher().process(iter([first, second])))
        self.assertEqual([packet.dts for packet in first_output.sent], [0])
        self.assertEqual([packet.dts for packet in second_output.sent], [0])
        self.assertEqual(first_output.closed, 1)
        self.assertEqual(second_output.closed, 1)

    def test_identical_settings_new_connection_reopens_output(self):
        first_output, second_output = Output(), Output()
        first, second = self.bypass_input(0), self.bypass_input(0)
        self.assertEqual(first.video_stream.codec_context, second.video_stream.codec_context)
        with patch("pipeworks.embedded.rtsp_publish.av.open",
                   side_effect=[first_output, second_output]) as opened:
            list(self.publisher().process(iter([first, second])))
        self.assertEqual(opened.call_count, 2)
        self.assertEqual(first_output.closed, 1)
        self.assertEqual(second_output.closed, 1)
        self.assertEqual([len(first_output.sent), len(second_output.sent)], [1, 1])

    def test_output_open_failure_and_invalid_time_base(self):
        publisher = self.publisher(reconnect=False)
        with patch(
            "pipeworks.embedded.rtsp_publish.av.open",
            side_effect=OSError("open failed"),
        ):
            self.assertEqual(list(publisher.process(iter([self.bypass_input(0)]))), [])

        input = self.bypass_input(0)
        input.packet.time_base = Fraction(-1)
        with patch("pipeworks.embedded.rtsp_publish.av.open", return_value=Output()):
            self.assertEqual(list(self.publisher().process(iter([input]))), [])

    def test_encoded_bytes_without_packet_are_rejected(self):
        input = PipelineContext(
            data=b"encoded",
            codec="h264",
            width=640,
            height=480,
            time_base=Fraction(1, 90000),
            fps=30,
        )
        self.assertEqual(list(self.publisher().process(iter([input]))), [])

    def test_input_error_closes_open_output(self):
        output = Output()

        def inputs():
            yield self.bypass_input(0)
            raise RuntimeError("input failed")

        with patch("pipeworks.embedded.rtsp_publish.av.open", return_value=output):
            with self.assertRaises(RuntimeError):
                list(self.publisher().process(inputs()))
        self.assertEqual(output.closed, 1)

    def test_copy_preserves_metadata_and_has_independent_payload_and_side_data(self):
        from pipeworks.embedded.rtsp_publish import _copy_packet_for_publish

        original = self.bypass_input(2, 3).packet
        original.is_keyframe = original.is_corrupt = True
        side = av.packet.PacketSideData(
            av.packet.packet_sidedata_type_from_literal("new_extradata"), 4,
        )
        side.update(b"abcd")
        original.set_sidedata(side, move=True)
        copied = _copy_packet_for_publish(original)
        self.assertIsNot(copied, original)
        self.assertNotEqual(copied.buffer_ptr, original.buffer_ptr)
        self.assertEqual(bytes(copied), bytes(original))
        self.assertEqual((copied.dts, copied.pts, copied.duration, copied.time_base),
                         (2, 3, 3000, Fraction(1, 90000)))
        self.assertTrue(copied.is_keyframe)
        self.assertTrue(copied.is_corrupt)
        self.assertEqual(bytes(copied.get_sidedata("new_extradata")), b"abcd")
        copied.update(b"xxxx")
        side = copied.get_sidedata("new_extradata")
        side.update(b"efgh")
        copied.set_sidedata(side, move=True)
        self.assertEqual(bytes(original), b"data")
        self.assertEqual(bytes(original.get_sidedata("new_extradata")), b"abcd")
        empty_times = _copy_packet_for_publish(av.Packet(b"data"))
        self.assertIsNone(empty_times.pts)
        self.assertIsNone(empty_times.dts)
        self.assertIsNone(empty_times.time_base)

    def test_unrepresentable_flags_are_explicit_errors(self):
        from pipeworks.embedded.rtsp_publish import _copy_packet_for_publish

        for flag in ("is_discard", "is_trusted", "is_disposable"):
            flags = dict.fromkeys(("is_discard", "is_trusted", "is_disposable"), False)
            flags[flag] = True
            with self.subTest(flag=flag), self.assertRaisesRegex(ValueError, flag):
                _copy_packet_for_publish(SimpleNamespace(**flags))

    def test_parallel_publishers_do_not_change_source_or_each_other(self):
        barrier = Barrier(2)

        class ConcurrentOutput(Output):
            def mux(self, packet):
                barrier.wait(timeout=3)
                if packet.stream is not self.stream:
                    raise AssertionError("다른 송신의 스트림이 연결되었습니다.")
                packet.update(b"xxxx")
                self.sent.append(packet)

        outputs = {url: ConcurrentOutput() for url in ("rtsp://one", "rtsp://two")}
        context = self.bypass_input(None, 3000)
        context.packet = av.Packet(b"data")
        context.packet.pts = 3000
        context.packet.duration = 3000
        with patch("pipeworks.embedded.rtsp_publish.av.open",
                   side_effect=lambda url, **kwargs: outputs[url]):
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [executor.submit(
                    lambda url=url: list(RTSPPublish(url, reconnect=False).process(iter([context])))
                ) for url in outputs]
                for future in futures:
                    future.result(timeout=5)
        self.assertEqual(bytes(context.packet), b"data")
        self.assertEqual(context.packet.pts, 3000)
        self.assertIsNone(context.packet.dts)
        self.assertIsNone(context.packet.time_base)
        self.assertIsNone(context.packet.stream)
        sent = [output.sent[0] for output in outputs.values()]
        self.assertIsNot(sent[0], sent[1])
        for packet, output in zip(sent, outputs.values()):
            self.assertIs(packet.stream, output.stream)
            self.assertEqual(packet.dts, 3000)

    def test_real_parallel_file_mux_preserves_source_and_decodes(self):
        from pipeworks.video import encoded_stream_info

        for codec, encoder_name in (("h264", "libx264"), ("hevc", "libx265")):
            with self.subTest(codec=codec):
                encoder = av.CodecContext.create(encoder_name, "w")
                encoder.width = encoder.height = 64
                encoder.pix_fmt = "yuv420p"
                encoder.time_base = Fraction(1, 30)
                encoder.options = {"preset": "ultrafast", "tune": "zerolatency"}
                if codec == "hevc":
                    encoder.options["x265-params"] = "log-level=error:pools=none"
                frame = av.VideoFrame(64, 64, "yuv420p")
                frame.pts = 0
                for plane in frame.planes:
                    plane.update(bytes([128]) * plane.buffer_size)
                packets = encoder.encode(frame) + encoder.encode(None)
                info = encoded_stream_info(CodecInfo(codec, 64, 64, pix_fmt="yuv420p"),
                                           bytes(packets[0]), Fraction(1, 30))
                before = [(bytes(p), p.pts, p.dts, p.time_base, p.stream) for p in packets]
                buffers = {url: BytesIO() for url in ("rtsp://one", "rtsp://two")}
                with patch("pipeworks.embedded.rtsp_publish.av.open", side_effect=(
                    lambda url, **kwargs: open_container(buffers[url], mode="w", format="matroska")
                )):
                    with ThreadPoolExecutor(max_workers=2) as executor:
                        futures = [executor.submit(
                            lambda url=url: list(RTSPPublish(url, reconnect=False).process(
                                iter(PipelineContext(packet=p, video_stream=info) for p in packets)
                            ))
                        ) for url in buffers]
                        for future in futures:
                            future.result(timeout=5)
                self.assertEqual(before,
                                 [(bytes(p), p.pts, p.dts, p.time_base, p.stream) for p in packets])
                for buffer in buffers.values():
                    buffer.seek(0)
                    with open_container(buffer) as result:
                        decoded = list(result.decode(video=0))
                    self.assertEqual(len(decoded), 1)
                    self.assertEqual((decoded[0].width, decoded[0].height), (64, 64))


if __name__ == "__main__":
    unittest.main()
