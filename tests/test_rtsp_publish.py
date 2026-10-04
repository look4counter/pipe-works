import sys
import unittest
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pipeworks.embedded.rtsp_publish import RTSPPublish
from pipeworks.models import PipelineContext


class Output:
    def __init__(self, fail_mux=False):
        self.stream = SimpleNamespace(time_base=Fraction(1, 90000))
        self.sent = []
        self.closed = 0
        self.fail_mux = fail_mux

    def add_stream_from_template(self, template):
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
    def publisher(self, **config):
        publisher = RTSPPublish("rtsp://output")
        publisher.configure(SimpleNamespace(**config))
        return publisher

    def bypass_input(self, dts, pts=None):
        stream = SimpleNamespace(
            index=0,
            codec_context=SimpleNamespace(name="h264", extradata=b""),
            width=640,
            height=480,
            time_base=Fraction(1, 90000),
        )
        packet = SimpleNamespace(
            dts=dts, pts=pts, duration=3000,
            time_base=Fraction(1, 90000), stream=None,
        )
        return PipelineContext(packet=packet, video_stream=stream)

    def test_bypass_repairs_dts_and_consumes_input(self):
        output = Output()
        first = self.bypass_input(3000, 3000)
        second = self.bypass_input(3000, 3000)
        second.video_stream = first.video_stream
        with patch("pipeworks.embedded.rtsp_publish.av.open", return_value=output), patch(
            "pipeworks.embedded.rtsp_publish.record_publish"
        ) as status:
            result = list(self.publisher().process(iter([first, second])))
        self.assertEqual([call.args[0] for call in status.call_args_list], [True, True])
        self.assertEqual(result, [])
        self.assertEqual(len(output.sent), 2)
        self.assertEqual(second.packet.dts, 6000)
        self.assertEqual(second.packet.pts, 6000)
        self.assertEqual(output.closed, 1)

    def test_bypass_fills_missing_dts(self):
        output = Output()
        first = self.bypass_input(0)
        second = self.bypass_input(None)
        second.video_stream = first.video_stream
        with patch("pipeworks.embedded.rtsp_publish.av.open", return_value=output):
            list(self.publisher().process(iter([first, second])))
        self.assertEqual(second.packet.dts, 3000)

    def test_output_options_follow_configuration(self):
        output = Output()
        publisher = self.publisher(transport="udp", timeout=10, packet_size=1200)
        with patch("pipeworks.embedded.rtsp_publish.av.open", return_value=output) as open_mock:
            list(publisher.process(iter([self.bypass_input(0)])))
        self.assertEqual(open_mock.call_args.kwargs["options"], {
            "rtsp_transport": "udp", "pkt_size": "1200", "timeout": "10000000",
        })

    def test_encoder_shape_uses_packet_path(self):
        output = Output()
        context = self.bypass_input(3000, 3000)
        encoded = PipelineContext(packet=context.packet, video_stream=context.video_stream)
        with patch("pipeworks.embedded.rtsp_publish.av.open", return_value=output):
            result = list(self.publisher().process(iter([encoded])))
        self.assertEqual(result, [])
        self.assertEqual(output.sent, [context.packet])
        self.assertEqual(output.closed, 1)

    def test_mux_failure_retries_or_raises_by_setting(self):
        failed = Output(fail_mux=True)
        recovered = Output()
        with patch("pipeworks.embedded.rtsp_publish.av.open", side_effect=[failed, recovered]), patch(
            "pipeworks.embedded.rtsp_publish.time.monotonic", side_effect=[0, 0, 1, 2]
        ), patch("pipeworks.embedded.rtsp_publish.record_publish") as status:
            result = list(self.publisher(reconnect_interval=1).process(iter([self.bypass_input(0)] * 3)))
        self.assertEqual([call.args[0] for call in status.call_args_list], [False, True, True])
        self.assertEqual(result, [])
        self.assertEqual(failed.closed, 1)
        self.assertEqual(len(recovered.sent), 2)
        self.assertEqual(recovered.closed, 1)

        failed = Output(fail_mux=True)
        with patch("pipeworks.embedded.rtsp_publish.av.open", return_value=failed):
            with self.assertRaises(OSError):
                list(self.publisher(reconnect=False).process(iter([self.bypass_input(0)])))
        self.assertEqual(failed.closed, 1)

    def test_stream_configuration_change_reopens_output(self):
        first_output = Output()
        second_output = Output()
        first = self.bypass_input(0)
        second = self.bypass_input(0)
        second.video_stream.width = 1280
        with patch("pipeworks.embedded.rtsp_publish.av.open", side_effect=[first_output, second_output]):
            list(self.publisher().process(iter([first, second])))
        self.assertEqual([packet.dts for packet in first_output.sent], [0])
        self.assertEqual([packet.dts for packet in second_output.sent], [0])
        self.assertEqual(first_output.closed, 1)
        self.assertEqual(second_output.closed, 1)

    def test_output_open_failure_and_invalid_time_base(self):
        publisher = self.publisher(reconnect=False)
        with patch("pipeworks.embedded.rtsp_publish.av.open", side_effect=OSError("open failed")):
            with self.assertRaises(OSError):
                list(publisher.process(iter([self.bypass_input(0)])))

        input = self.bypass_input(0)
        input.packet.time_base = Fraction(-1)
        with patch("pipeworks.embedded.rtsp_publish.av.open", return_value=Output()):
            with self.assertRaises(ValueError):
                list(self.publisher().process(iter([input])))

    def test_encoded_bytes_without_packet_are_rejected(self):
        input = PipelineContext(
            data=b"encoded", codec="h264", width=640, height=480,
            time_base=Fraction(1, 90000), fps=30,
        )
        with self.assertRaises(ValueError):
            list(self.publisher().process(iter([input])))

    def test_input_error_closes_open_output(self):
        output = Output()

        def inputs():
            yield self.bypass_input(0)
            raise RuntimeError("input failed")

        with patch("pipeworks.embedded.rtsp_publish.av.open", return_value=output):
            with self.assertRaises(RuntimeError):
                list(self.publisher().process(inputs()))
        self.assertEqual(output.closed, 1)


if __name__ == "__main__":
    unittest.main()
