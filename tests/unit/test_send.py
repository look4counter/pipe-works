from fractions import Fraction
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from pipeline.arguments import PipelineArguments
from pipeline.context import EncodedPacket, ReceivePacket
from pipeline import send as send_module


def parameters() -> PipelineArguments:
    return PipelineArguments(
        "rtsp://camera/input", "tcp", "rtsp://server/output", "udp", "nvidia", 0,
        False, None, False, None, 3, None, False, None, fps=30,
    )


def packet(data: bytes, codec: str = "h264", width: int = 640) -> EncodedPacket:
    return EncodedPacket(
        video_stream=object(), data=data, time_base=Fraction(1, 30),
        codec=codec, width=width, height=480,
    )


def test_send_configures_stream_and_assigns_monotonic_timestamps(monkeypatch) -> None:
    output_stream = SimpleNamespace()
    output = Mock()
    output.add_stream.return_value = output_stream
    muxed_packets = []

    class FakePacket:
        def __init__(self, data: bytes) -> None:
            self.data = data
            muxed_packets.append(self)

    monkeypatch.setattr(send_module.av, "open", Mock(return_value=output))
    monkeypatch.setattr(send_module.av, "Packet", FakePacket)

    send_module.send(parameters(), iter([packet(b"one"), packet(b"two")]))

    send_module.av.open.assert_called_once_with(
        "rtsp://server/output",
        mode="w",
        format="rtsp",
        options={
            "rtsp_transport": "udp",
            "pkt_size": "1452",
            "rw_timeout": "5000000",
            "timeout": "5000000",
        },
    )
    output.add_stream.assert_called_once_with("h264", rate=30)
    assert output_stream.width == 640
    assert output_stream.height == 480
    assert output_stream.time_base == Fraction(1, 30)
    assert [(item.pts, item.dts) for item in muxed_packets] == [(0, 0), (1, 1)]
    assert all(item.stream is output_stream for item in muxed_packets)
    assert output.mux.call_count == 2
    output.close.assert_called_once_with()


def test_send_scales_pts_increment_from_time_base_and_fps(monkeypatch) -> None:
    output = Mock()
    output.add_stream.return_value = SimpleNamespace()
    muxed_packets = []

    class FakePacket:
        def __init__(self, data: bytes) -> None:
            self.data = data
            muxed_packets.append(self)

    monkeypatch.setattr(send_module.av, "open", Mock(return_value=output))
    monkeypatch.setattr(send_module.av, "Packet", FakePacket)
    source = [
        EncodedPacket(object(), b"one", Fraction(1, 90000), "h264", 640, 480),
        EncodedPacket(object(), b"two", Fraction(1, 90000), "h264", 640, 480),
    ]

    send_module.send(parameters(), iter(source))

    assert [(item.pts, item.dts) for item in muxed_packets] == [(0, 0), (3000, 3000)]


def test_send_wraps_pts_at_unsigned_32_bit_limit(monkeypatch) -> None:
    output = Mock()
    output.add_stream.return_value = SimpleNamespace()
    muxed_packets = []

    class FakePacket:
        def __init__(self, data: bytes) -> None:
            self.data = data
            muxed_packets.append(self)

    monkeypatch.setattr(send_module.av, "open", Mock(return_value=output))
    monkeypatch.setattr(send_module.av, "Packet", FakePacket)
    monkeypatch.setattr(send_module, "PTS_MODULUS", 4)

    send_module.send(parameters(), iter([packet(b"1"), packet(b"2"), packet(b"3"), packet(b"4"), packet(b"5")]))

    assert [item.pts for item in muxed_packets] == [0, 1, 2, 3, 0]


def test_send_bypass_repairs_duplicate_dts_and_forwards_packet(monkeypatch) -> None:
    output_stream = SimpleNamespace(time_base=Fraction(1, 90000))
    output = Mock()
    output.add_stream_from_template.return_value = output_stream
    muxed_timestamps = []

    class FakePacket:
        def __init__(self, pts: int, dts: int) -> None:
            self.pts = pts
            self.dts = dts
            self.time_base = Fraction(1, 90000)
            self.duration = 3000
            self.size = 100
            self.is_keyframe = False
            self.stream = None

    video_stream = SimpleNamespace(
        index=0,
        codec_context=SimpleNamespace(name="h264", extradata=b""),
        width=640,
        height=480,
        time_base=Fraction(1, 90000),
    )
    first_packet = FakePacket(9000, 9000)
    first_packet.dts = None
    first_packet.time_base = None
    received = [
        ReceivePacket(video_stream, first_packet),
        ReceivePacket(video_stream, FakePacket(9000, 9000)),
    ]
    output.mux.side_effect = lambda item: muxed_timestamps.append((item.pts, item.dts))
    monkeypatch.setattr(send_module.av, "open", Mock(return_value=output))
    anomalous_before = send_module.PIPELINE_STATISTICS.snapshot()["anomalous"]

    send_module.send_bypass(parameters(), iter(received))

    assert muxed_timestamps == [(9000, 9000), (12000, 12000)]
    assert send_module.PIPELINE_STATISTICS.snapshot()["anomalous"] == anomalous_before + 2


def test_send_reopens_output_when_encoded_format_changes(monkeypatch) -> None:
    first_output, second_output = Mock(), Mock()
    first_output.add_stream.return_value = SimpleNamespace()
    second_output.add_stream.return_value = SimpleNamespace()
    outputs = iter([first_output, second_output])
    opened = []

    def open_output(*args, **kwargs):
        opened.append((args, kwargs))
        return next(outputs)

    class FakePacket:
        def __init__(self, data: bytes) -> None:
            self.data = data

    monkeypatch.setattr(send_module.av, "open", open_output)
    monkeypatch.setattr(send_module.av, "Packet", FakePacket)

    send_module.send(
        parameters(),
        iter([packet(b"h264"), packet(b"hevc", codec="hevc", width=1280)]),
    )

    assert len(opened) == 2
    first_output.close.assert_called_once_with()
    second_output.close.assert_called_once_with()
    assert first_output.add_stream.call_args.args == ("h264",)
    assert second_output.add_stream.call_args.args == ("hevc",)


@pytest.mark.parametrize(
    "encoded_packet",
    [
        EncodedPacket(object(), b"data", Fraction(1, 30), None, 640, 480),
        EncodedPacket(object(), b"data", None, "h264", 640, 480),
    ],
)
def test_send_rejects_incomplete_encoded_stream_metadata(monkeypatch, encoded_packet) -> None:
    open_output = Mock()
    monkeypatch.setattr(send_module.av, "open", open_output)

    with pytest.raises(ValueError):
        send_module.send(parameters(), iter([encoded_packet]))
    open_output.assert_not_called()
