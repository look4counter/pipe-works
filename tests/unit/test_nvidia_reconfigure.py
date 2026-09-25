from contextlib import nullcontext
from fractions import Fraction
from types import SimpleNamespace
from unittest.mock import Mock
import sys

from pipeline.arguments import PipelineArguments
from pipeline.context import FrameContext, ReceivePacket
from pipeline.nvidia_pipe.decode import nvidia_decode
from pipeline.nvidia_pipe.encode import nvidia_encode


def parameters() -> PipelineArguments:
    return PipelineArguments(
        "rtsp://in", "tcp", "rtsp://out", "tcp", "nvidia", 0,
        False, None, False, None, 3, None, False, None, fps=30,
    )


def video_stream(codec: str, width: int, height: int, extradata: bytes) -> object:
    return SimpleNamespace(
        codec=SimpleNamespace(name=codec),
        codec_context=SimpleNamespace(
            width=width, height=height, extradata=extradata
        ),
    )


def test_decoder_is_recreated_when_input_codec_changes(monkeypatch) -> None:
    streams = [
        video_stream("h264", 640, 480, b"h264-config"),
        video_stream("hevc", 1280, 720, b"hevc-config"),
    ]
    first_frame, second_frame = object(), object()
    decoders = [Mock(), Mock()]
    for decoder, frame in zip(decoders, (first_frame, second_frame)):
        decoder.GetPixelFormat.return_value = SimpleNamespace(name="NV12")
        decoder.Decode.return_value = [frame]
        decoder.Flush.return_value = []
    create_decoder = Mock(side_effect=decoders)
    monkeypatch.setitem(
        sys.modules,
        "PyNvVideoCodec",
        SimpleNamespace(
            cudaVideoCodec=SimpleNamespace(H264="h264-id", HEVC="hevc-id"),
            OutputColorType=SimpleNamespace(NATIVE="native"),
            DisplayDecodeLatencyType=SimpleNamespace(NATIVE="native"),
            PacketData=type("PacketData", (), {}),
            CreateDecoder=create_decoder,
        ),
    )
    streams_created = iter(
        [SimpleNamespace(cuda_stream=11), SimpleNamespace(cuda_stream=22)]
    )
    monkeypatch.setattr(
        "pipeline.nvidia_pipe.decode.torch.cuda.Stream",
        lambda **_: next(streams_created),
    )
    monkeypatch.setattr(
        "pipeline.nvidia_pipe.decode.torch.cuda.stream", lambda _: nullcontext()
    )
    packets = [ReceivePacket(streams[0], b"first"), ReceivePacket(streams[1], b"second")]

    frames = list(nvidia_decode(parameters(), iter(packets)))

    assert create_decoder.call_count == 2
    assert [frame.codec for frame in frames] == ["h264", "hevc"]
    assert [frame.width for frame in frames] == [640, 1280]
    assert [frame.data for frame in frames] == [first_frame, second_frame]
    assert all(decoder.Flush.call_count == 1 for decoder in decoders)


def test_decoder_flushes_delayed_frames_on_stop(monkeypatch) -> None:
    stream = video_stream("h264", 640, 480, b"config")
    decoded_frame, delayed_frame = object(), object()
    decoder = Mock()
    decoder.GetPixelFormat.return_value = SimpleNamespace(name="NV12")
    decoder.Decode.return_value = [decoded_frame]
    decoder.Flush.return_value = [delayed_frame]
    monkeypatch.setitem(
        sys.modules,
        "PyNvVideoCodec",
        SimpleNamespace(
            cudaVideoCodec=SimpleNamespace(H264="h264-id", HEVC="hevc-id"),
            OutputColorType=SimpleNamespace(NATIVE="native"),
            DisplayDecodeLatencyType=SimpleNamespace(NATIVE="native"),
            PacketData=type("PacketData", (), {}),
            CreateDecoder=Mock(return_value=decoder),
        ),
    )
    monkeypatch.setattr(
        "pipeline.nvidia_pipe.decode.torch.cuda.Stream",
        lambda **_: SimpleNamespace(cuda_stream=11),
    )
    monkeypatch.setattr(
        "pipeline.nvidia_pipe.decode.torch.cuda.stream", lambda _: nullcontext()
    )

    frames = list(nvidia_decode(parameters(), iter([ReceivePacket(stream, b"packet")])))

    assert [frame.data for frame in frames] == [decoded_frame, delayed_frame]
    decoder.Flush.assert_called_once_with()


def test_encoder_is_flushed_and_recreated_when_frame_format_changes(monkeypatch) -> None:
    first_encoder, second_encoder = Mock(), Mock()
    first_encoder.Encode.return_value = [b"first"]
    first_encoder.EndEncode.return_value = [b"first-flush"]
    second_encoder.Encode.return_value = [b"second"]
    second_encoder.EndEncode.return_value = [b"second-flush"]
    create_encoder = Mock(side_effect=[first_encoder, second_encoder])
    monkeypatch.setitem(
        sys.modules,
        "PyNvVideoCodec",
        SimpleNamespace(CreateEncoder=create_encoder),
    )
    monkeypatch.setattr(
        "pipeline.nvidia_pipe.encode.torch.cuda.stream", lambda _: nullcontext()
    )
    first_stream = SimpleNamespace(cuda_stream=11)
    second_stream = SimpleNamespace(cuda_stream=22)
    frames = [
        FrameContext(object(), "frame1", first_stream, "NV12", "h264", 640, 480),
        FrameContext(object(), "frame2", second_stream, "NV12", "hevc", 1280, 720),
    ]

    packets = list(nvidia_encode(parameters(), iter(frames)))

    assert create_encoder.call_count == 2
    assert [packet.data for packet in packets] == [
        b"first", b"first-flush", b"second", b"second-flush"
    ]
    assert [packet.codec for packet in packets] == ["h264", "h264", "hevc", "hevc"]
    assert [packet.width for packet in packets] == [640, 640, 1280, 1280]
    assert all(packet.time_base == Fraction(1, 30) for packet in packets)
