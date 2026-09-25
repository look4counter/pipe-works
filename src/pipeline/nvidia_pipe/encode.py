from collections.abc import Iterator
import torch
from fractions import Fraction
from time import perf_counter_ns

from pipeline.arguments import PipelineArguments
from pipeline.context import FrameContext
from pipeline.context import EncodedPacket
from pipeline.statistics import PIPELINE_STATISTICS
TIMING_REPORT_INTERVAL_NS = 1_000_000_000


def encoded_bytes(encoded) -> bytes:
    if isinstance(encoded, (bytes, bytearray, memoryview)):
        return bytes(encoded)
    if isinstance(encoded, dict):
        for key in ("bitstream", "data", "packet", "encoded_data", "payload"):
            if key in encoded:
                value = encoded[key]
                if isinstance(value, (bytes, bytearray, memoryview)):
                    return bytes(value)
                if isinstance(value, (list, tuple)):
                    return bytes(value)
        for value in encoded.values():
            if isinstance(value, (bytes, bytearray, memoryview)):
                return bytes(value)
            if isinstance(value, (dict, list, tuple)):
                try:
                    return encoded_bytes(value)
                except TypeError:
                    continue
    if isinstance(encoded, (list, tuple)):
        if all(isinstance(value, int) for value in encoded):
            return bytes(encoded)
        for value in encoded:
            try:
                return encoded_bytes(value)
            except TypeError:
                continue
    raise TypeError(f"지원하지 않는 인코더 패킷 타입: {type(encoded).__name__}")


def nvidia_encode(
    parameters: PipelineArguments, decoded_frames: Iterator[FrameContext]
) -> Iterator[EncodedPacket]:
    import PyNvVideoCodec as nvc

    encoder = None
    encoder_configuration = None
    encoder_metadata = None
    timing_window_started_at_ns = perf_counter_ns()
    interval_frame_count = 0
    interval_elapsed_ns = 0
    report_frame_count = 0
    report_elapsed_ns = 0

    def wrap_packets(encoded_packets, metadata):
        for encoded_packet in encoded_packets:
            yield EncodedPacket(
                metadata["video_stream"],
                encoded_bytes(encoded_packet),
                metadata["time_base"],
                metadata["codec"],
                metadata["width"],
                metadata["height"],
            )

    for decoded_frame in decoded_frames:
        configuration = (
            decoded_frame.video_stream,
            decoded_frame.codec,
            decoded_frame.width,
            decoded_frame.height,
            decoded_frame.pixel_format,
            decoded_frame.cuda_stream.cuda_stream,
        )

        if configuration != encoder_configuration:
            if encoder is not None:
                yield from wrap_packets(encoder.EndEncode(), encoder_metadata)

            time_base = Fraction(1, parameters.fps)
            codec = decoded_frame.codec
            width = decoded_frame.width
            height = decoded_frame.height
            video_stream = decoded_frame.video_stream
            encoder_metadata = {
                "video_stream": video_stream,
                "time_base": time_base,
                "codec": codec,
                "width": width,
                "height": height,
            }

            encoder_kwargs = {
                "gpu_id": parameters.gpu_id,
                "codec": decoded_frame.codec,
                "bf": 0,
                "fps": parameters.fps,
                "gop": parameters.fps,
                "idrperiod": parameters.fps,
                "cudastream": decoded_frame.cuda_stream.cuda_stream,
            }

            encoder = nvc.CreateEncoder(
                decoded_frame.width,
                decoded_frame.height,
                decoded_frame.pixel_format,
                False,
                **encoder_kwargs,
            )
            encoder_configuration = configuration

        with torch.cuda.stream(decoded_frame.cuda_stream):
            encoded_packets = encoder.Encode(decoded_frame.data)
        encode_returned_at_ns = perf_counter_ns()

        ready_packets = list(wrap_packets(encoded_packets, encoder_metadata))
        if decoded_frame.decode_started_at_ns is not None:
            elapsed_ns = encode_returned_at_ns - decoded_frame.decode_started_at_ns
            interval_elapsed_ns += elapsed_ns
            interval_frame_count += 1

            if interval_frame_count >= parameters.inference_interval:
                report_elapsed_ns += interval_elapsed_ns
                report_frame_count += interval_frame_count
                interval_elapsed_ns = 0
                interval_frame_count = 0

            if (
                encode_returned_at_ns - timing_window_started_at_ns
                >= TIMING_REPORT_INTERVAL_NS
            ):
                # Include a final partial group so every measured frame appears
                # in this report; each group contains at most inference_interval frames.
                if interval_frame_count:
                    report_elapsed_ns += interval_elapsed_ns
                    report_frame_count += interval_frame_count
                    interval_elapsed_ns = 0
                    interval_frame_count = 0

                if report_frame_count:
                    average_ms = report_elapsed_ns / report_frame_count / 1_000_000
                    PIPELINE_STATISTICS.set_average_ms(average_ms)

                timing_window_started_at_ns = encode_returned_at_ns
                report_elapsed_ns = 0
                report_frame_count = 0
        yield from ready_packets

    if encoder is not None:
        yield from wrap_packets(encoder.EndEncode(), encoder_metadata)
