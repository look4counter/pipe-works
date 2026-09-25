from collections.abc import Iterator
from time import perf_counter_ns

import torch
import ctypes

from pipeline.arguments import PipelineArguments
from pipeline.context import ReceivePacket, FrameContext
from pipeline.statistics import PIPELINE_STATISTICS


def _decoded_frame_pts(frame: object) -> int | None:
    pts = getattr(frame, "timestamp", None)
    if pts is None:
        get_pts = getattr(frame, "getPTS", None)
        if callable(get_pts):
            pts = get_pts()
    return int(pts) if pts is not None else None


def _stream_configuration(received_packet: ReceivePacket) -> tuple[object, ...]:
    stream = received_packet.video_stream
    codec_context = stream.codec_context
    extradata = getattr(codec_context, "extradata", None) or b""
    return (
        stream,
        stream.codec.name.lower(),
        codec_context.width,
        codec_context.height,
        bytes(extradata),
    )


def _frame_context(
    decoded_frame: object,
    metadata: dict[str, object],
    decode_started_at_ns: int,
) -> FrameContext:
    PIPELINE_STATISTICS.observe_decoded_pts(_decoded_frame_pts(decoded_frame))
    return FrameContext(
        metadata["video_stream"],
        decoded_frame,
        metadata["cuda_stream"],
        metadata["pixel_format"],
        metadata["codec"],
        metadata["width"],
        metadata["height"],
        decode_started_at_ns=decode_started_at_ns,
    )


def nvidia_decode(
    parameters: PipelineArguments, received_packets: Iterator[ReceivePacket]
) -> Iterator[FrameContext]:
    import PyNvVideoCodec as nvc

    decoder = None
    decoder_configuration = None
    decoder_metadata: dict[str, object] | None = None

    for received_packet in received_packets:
        configuration = _stream_configuration(received_packet)
        if configuration != decoder_configuration:
            if decoder is not None and decoder_metadata is not None:
                with torch.cuda.stream(decoder_metadata["cuda_stream"]):
                    decode_started_at_ns = perf_counter_ns()
                    flushed_frames = decoder.Flush()
                for decoded_frame in flushed_frames:
                    yield _frame_context(
                        decoded_frame, decoder_metadata, decode_started_at_ns
                    )

            PIPELINE_STATISTICS.reset_decode_order()
            codec_ids = {
                "h264": nvc.cudaVideoCodec.H264,
                "hevc": nvc.cudaVideoCodec.HEVC,
                "h265": nvc.cudaVideoCodec.HEVC,
            }

            _, codec, width, height, _ = configuration

            cuda_stream = torch.cuda.Stream(device=parameters.gpu_id)

            decoder_kwargs = {
                "gpuid": parameters.gpu_id,
                "codec": codec_ids[codec],
                "usedevicememory": True,
                "outputColorType": nvc.OutputColorType.NATIVE,
                "latency": nvc.DisplayDecodeLatencyType.NATIVE,
                "cudastream": cuda_stream.cuda_stream,
            }

            decoder = nvc.CreateDecoder(**decoder_kwargs)
            pixel_format = decoder.GetPixelFormat()
            decoder_configuration = configuration
            decoder_metadata = {
                "video_stream": received_packet.video_stream,
                "cuda_stream": cuda_stream,
                "pixel_format": pixel_format.name,
                "codec": codec,
                "width": width,
                "height": height,
            }

        packet_data = nvc.PacketData()
        bitstream = ctypes.create_string_buffer(bytes(received_packet.data))
        packet_data.bsl_data = ctypes.addressof(bitstream)
        packet_data.bsl = len(bitstream) - 1
        packet_pts = getattr(received_packet.data, "pts", None)
        if packet_pts is not None:
            packet_data.pts = int(packet_pts)

        with torch.cuda.stream(cuda_stream):
            decode_started_at_ns = perf_counter_ns()
            frames = decoder.Decode(packet_data)
            for frame in frames:
                yield _frame_context(frame, decoder_metadata, decode_started_at_ns)

    # The receive iterator ends normally when its stop event is set. Flush the
    # decoder then so delayed B-frames continue through inference and encoding.
    if decoder is not None and decoder_metadata is not None:
        with torch.cuda.stream(decoder_metadata["cuda_stream"]):
            decode_started_at_ns = perf_counter_ns()
            flushed_frames = decoder.Flush()
        for decoded_frame in flushed_frames:
            yield _frame_context(
                decoded_frame, decoder_metadata, decode_started_at_ns
            )
