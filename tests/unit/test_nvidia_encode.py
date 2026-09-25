from contextlib import nullcontext
from fractions import Fraction
from types import SimpleNamespace
from unittest.mock import Mock
import sys

import pytest

from pipeline.arguments import PipelineArguments
from pipeline.context import EncodedPacket, FrameContext, ReceivePacket
from pipeline.nvidia_pipe.encode import encoded_bytes, nvidia_encode
from pipeline.nvidia_pipe.decode import nvidia_decode


@pytest.mark.parametrize(
    "value, expected",
    [
        (b"packet", b"packet"),
        (bytearray(b"packet"), b"packet"),
        (memoryview(b"packet"), b"packet"),
        ([112, 107, 116], b"pkt"),
        ({"bitstream": b"packet"}, b"packet"),
        ({"payload": {"data": b"packet"}}, b"packet"),
    ],
)
def test_encoded_bytes_converts_supported_payloads(value, expected: bytes) -> None:
    assert encoded_bytes(value) == expected


def test_encoded_bytes_rejects_unknown_payload() -> None:
    with pytest.raises(TypeError):
        encoded_bytes(object())


def test_nvidia_encode_uses_encoder_api_and_flushes(monkeypatch) -> None:
    video_stream = object()
    cuda_stream = SimpleNamespace(cuda_stream=456)
    frame = FrameContext(
        video_stream, object(), cuda_stream, "NV12", "h264", 640, 480
    )
    encoder = Mock()
    encoder.Encode.return_value = [{"bitstream": b"encoded"}]
    encoder.EndEncode.return_value = [b"flush"]
    create_encoder = Mock(return_value=encoder)
    monkeypatch.setitem(
        sys.modules,
        "PyNvVideoCodec",
        SimpleNamespace(CreateEncoder=create_encoder),
    )
    monkeypatch.setattr("pipeline.nvidia_pipe.encode.torch.cuda.stream", lambda _: nullcontext())
    parameters = PipelineArguments(
        "rtsp://in", "tcp", "rtsp://out", "tcp", "nvidia", 0,
        False, None, False, None, 3, None, False, None, fps=25,
    )

    packets = list(nvidia_encode(parameters, iter([frame])))

    create_encoder.assert_called_once_with(
        640,
        480,
        "NV12",
        False,
        gpu_id=0,
        codec="h264",
        bf=0,
        fps=25,
        gop=25,
        idrperiod=25,
        cudastream=456,
    )
    assert [packet.data for packet in packets] == [b"encoded", b"flush"]
    assert all(isinstance(packet, EncodedPacket) for packet in packets)
    assert packets[0].time_base == Fraction(1, 25)


def test_nvidia_decode_uses_decoder_api_without_gpu(monkeypatch) -> None:
    video_stream = SimpleNamespace(
        codec=SimpleNamespace(name="h264"),
        codec_context=SimpleNamespace(width=640, height=480),
    )
    fake_frame = object()
    decoder = Mock()
    decoder.GetPixelFormat.return_value = SimpleNamespace(name="NV12")
    decoder.Decode.return_value = [fake_frame]
    decoder.Flush.return_value = []
    create_decoder = Mock(return_value=decoder)
    codec_ids = SimpleNamespace(H264="h264-codec", HEVC="hevc-codec")
    nvc = SimpleNamespace(
        cudaVideoCodec=codec_ids,
        OutputColorType=SimpleNamespace(NATIVE="native"),
        DisplayDecodeLatencyType=SimpleNamespace(NATIVE="native-latency"),
        PacketData=type("PacketData", (), {}),
        CreateDecoder=create_decoder,
    )
    monkeypatch.setitem(sys.modules, "PyNvVideoCodec", nvc)
    cuda_stream = SimpleNamespace(cuda_stream=789)
    monkeypatch.setattr("pipeline.nvidia_pipe.decode.torch.cuda.Stream", lambda **_: cuda_stream)
    monkeypatch.setattr("pipeline.nvidia_pipe.decode.torch.cuda.stream", lambda _: nullcontext())
    parameters = PipelineArguments(
        "rtsp://in", "tcp", "rtsp://out", "tcp", "nvidia", 2,
        False, None, False, None, 3, None, False, None,
    )
    received = ReceivePacket(video_stream, b"compressed")

    frames = list(nvidia_decode(parameters, iter([received])))

    create_decoder.assert_called_once_with(
        gpuid=2,
        codec="h264-codec",
        usedevicememory=True,
        outputColorType="native",
        latency="native-latency",
        cudastream=789,
    )
    assert frames[0].data is fake_frame
    assert frames[0].pixel_format == "NV12"
    decoder.Decode.assert_called_once()


def test_nvidia_encode_propagates_encoder_initialization_error(monkeypatch) -> None:
    frame = FrameContext(object(), object(), SimpleNamespace(cuda_stream=1), "NV12", "h264", 2, 2)
    create_encoder = Mock(side_effect=RuntimeError("encoder unavailable"))
    monkeypatch.setitem(
        sys.modules,
        "PyNvVideoCodec",
        SimpleNamespace(CreateEncoder=create_encoder),
    )
    parameters = PipelineArguments(
        "rtsp://in", "tcp", "rtsp://out", "tcp", "nvidia", 0,
        False, None, False, None, 3, None, False, None,
    )

    with pytest.raises(RuntimeError, match="encoder unavailable"):
        next(nvidia_encode(parameters, iter([frame])))
