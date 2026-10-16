from dataclasses import FrozenInstanceError, fields
from fractions import Fraction
from io import BytesIO
from types import SimpleNamespace
import unittest

import av
import numpy as np

from pipeworks.video import CodecInfo, VideoStreamInfo, encoded_stream_info


class VideoInfoTests(unittest.TestCase):
    def test_invalid_dimensions_are_rejected(self):
        with self.assertRaises(ValueError):
            CodecInfo("h264", 0, 64)
        with self.assertRaises(ValueError):
            CodecInfo("", 64, 64)
        data = bytearray(b"header")
        info = CodecInfo("h264", 64, 64, data)
        data[0] = 0
        self.assertEqual(info.extradata, b"header")

    def test_snapshot_contains_only_values_and_is_immutable(self):
        extra = bytearray(b"header")
        source = SimpleNamespace(
            codec_context=SimpleNamespace(
                name="h264", width=640, height=480, extradata=extra, pix_fmt="yuv420p"
            ),
            time_base=Fraction(1, 90000), average_rate=Fraction(30), index=2,
        )
        info = VideoStreamInfo.from_stream(source)
        other = VideoStreamInfo.from_stream(source)
        extra[0] = 0
        source.codec_context = None
        self.assertEqual(info.codec_context.extradata, b"header")
        self.assertEqual((info.codec.name, info.width, info.height), ("h264", 640, 480))
        self.assertNotEqual(info.connection_id, other.connection_id)
        self.assertFalse(hasattr(info, "container"))
        self.assertTrue(all(getattr(info, f.name) is not source for f in fields(info)))
        with self.assertRaises(FrozenInstanceError):
            info.codec_context.width = 1
        with self.assertRaises(FrozenInstanceError):
            info.connection_id = "other"

    def test_encoded_headers_use_actual_output_and_new_generation(self):
        original = VideoStreamInfo(CodecInfo("h264", 64, 64, b"old"))
        data = b"\x00\x00\x00\x01\x67sps\x00\x00\x01\x68pps\x00\x00\x01\x65frame"
        info = encoded_stream_info(original, data, Fraction(1, 30))
        self.assertEqual(info.codec_context.extradata,
                         b"\x00\x00\x00\x01\x67sps\x00\x00\x00\x01\x68pps")
        self.assertEqual(info.time_base, Fraction(1, 30))
        self.assertEqual(info.average_rate, Fraction(30))
        self.assertNotEqual(info.connection_id, original.connection_id)
        self.assertNotIn(b"old", info.codec_context.extradata)

    def test_real_pyav_roundtrip_after_source_close(self):
        for codec, encoder in [("h264", "libx264"), ("hevc", "libx265")]:
            for containerized in (False, True):
                with self.subTest(codec=codec, containerized=containerized):
                    raw = BytesIO()
                    with av.open(raw, "w", format="matroska" if containerized else codec) as output:
                        stream = output.add_stream(encoder, rate=30)
                        stream.width = stream.height = 64
                        stream.pix_fmt = "yuv420p"
                        stream.options = {"preset": "ultrafast", "tune": "zerolatency"}
                        if codec == "hevc":
                            stream.options["x265-params"] = "log-level=error:pools=none"
                        frame = av.VideoFrame.from_ndarray(np.zeros((64, 64, 3), dtype=np.uint8), format="rgb24")
                        for packet in stream.encode(frame) + stream.encode(None):
                            output.mux(packet)
                    raw.seek(0)
                    with av.open(raw, format="matroska" if containerized else codec) as source:
                        info = VideoStreamInfo.from_stream(source.streams.video[0])
                        packets = []
                        for packet in source.demux(video=0):
                            if packet.size:
                                packets.append(bytes(packet))
                    # 원본 컨테이너가 닫힌 후 독립 값만으로 송출한다.
                    if not containerized:
                        info = encoded_stream_info(info, packets[0], Fraction(1, 30))
                        self.assertTrue(info.codec_context.extradata)
                    remuxed = BytesIO()
                    with av.open(remuxed, "w", format="matroska") as output:
                        restored = info.add_to_output(output)
                        output.start_encoding()
                        self.assertFalse(restored.codec_context.is_open)
                        self.assertEqual(restored.codec_context.extradata, info.codec_context.extradata)
                        for i, data in enumerate(packets):
                            packet = av.Packet(data)
                            packet.pts = packet.dts = i
                            packet.time_base = Fraction(1, 30)
                            packet.stream = restored
                            output.mux(packet)
                    remuxed.seek(0)
                    with av.open(remuxed) as result:
                        decoded = list(result.decode(video=0))
                        self.assertEqual(len(decoded), 1)
                        self.assertEqual((decoded[0].width, decoded[0].height), (64, 64))


if __name__ == "__main__":
    unittest.main()
