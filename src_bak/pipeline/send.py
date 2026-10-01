import logging
import time
from collections.abc import Iterator
from fractions import Fraction
from itertools import chain
from math import ceil

import av

from pipeline.arguments import PipelineArguments
from pipeline.context import EncodedPacket, ReceivePacket
from pipeline.statistics import PIPELINE_STATISTICS

logger = logging.getLogger(__name__)
PTS_MODULUS = 1 << 32
RTSP_PACKET_SIZE = 1452
RTSP_IO_TIMEOUT_SECONDS = 5
RTSP_IO_TIMEOUT_MICROSECONDS = RTSP_IO_TIMEOUT_SECONDS * 1_000_000
OUTPUT_RECONNECT_INTERVAL_SECONDS = 3.0


def _rtsp_output_options(transport: str) -> dict[str, str]:
    timeout = str(RTSP_IO_TIMEOUT_MICROSECONDS)
    return {
        "rtsp_transport": transport,
        "pkt_size": str(RTSP_PACKET_SIZE),
        "timeout": timeout,
    }


def _close_output(output) -> None:
    if output is None:
        return
    try:
        output.close()
    except Exception:
        logger.error("Error while closing RTSP output", exc_info=True)


def _pts_increment(time_base: Fraction, fps: int) -> int:
    """Return integer time-base ticks per frame for the configured frame rate."""
    if fps <= 0:
        raise ValueError("fps must be a positive integer")
    frame_ticks = Fraction(1, fps) / time_base
    if frame_ticks.denominator != 1:
        raise ValueError(
            f"fps {fps} cannot be represented exactly with time_base {time_base}"
        )
    return frame_ticks.numerator


def _next_dts(previous_dts: int, previous_time_base, time_base, fps: int) -> int:
    """Compute DTS at least one configured frame after the previous DTS."""
    if fps <= 0:
        raise ValueError("fps must be a positive integer")
    previous_time_base = Fraction(previous_time_base)
    time_base = Fraction(time_base)
    if previous_time_base <= 0 or time_base <= 0:
        raise ValueError("packet time_base must be positive")
    next_timestamp = Fraction(previous_dts) * previous_time_base + Fraction(1, fps)
    return ceil(next_timestamp / time_base)


def send_bypass(
    parameters: PipelineArguments, received_packets: Iterator[ReceivePacket]
) -> None:
    """Remux compressed input packets without decoding or re-encoding."""
    output = None
    output_stream = None
    active_configuration = None
    last_dts = None
    retry_at = 0.0
    try:
        for received in received_packets:
            input_stream = received.video_stream
            packet = received.data
            codec_context = input_stream.codec_context
            configuration = (
                getattr(input_stream, "index", None),
                codec_context.name,
                input_stream.width,
                input_stream.height,
                bytes(codec_context.extradata or b""),
                input_stream.time_base,
            )
            if configuration != active_configuration:
                _close_output(output)
                output = None
                output_stream = None
                active_configuration = configuration
                last_dts = None

            packet_dts = packet.dts
            packet_time_base = (
                packet.time_base
                or input_stream.time_base
                or (output_stream.time_base if output_stream is not None else None)
            )
            if packet_time_base is None:
                raise ValueError("Cannot repair packet DTS without a time_base")
            if packet.time_base is None:
                packet.time_base = packet_time_base
            if packet_dts is None:
                if packet.pts is not None:
                    packet_dts = packet.pts
                elif last_dts is not None:
                    packet_dts = _next_dts(
                        last_dts[0], last_dts[1], packet_time_base, parameters.fps
                    )
                else:
                    packet_dts = 0
                packet.dts = packet_dts
                PIPELINE_STATISTICS.increment("anomalous")
            if packet_dts is not None and last_dts is not None:
                previous_time = Fraction(last_dts[0]) * Fraction(last_dts[1])
                current_time = Fraction(packet_dts) * Fraction(packet_time_base)
                if current_time <= previous_time:
                    corrected_dts = _next_dts(
                        last_dts[0], last_dts[1], packet_time_base, parameters.fps
                    )
                    correction = corrected_dts - packet_dts
                    packet.dts = corrected_dts
                    if packet.pts is not None:
                        packet.pts += correction
                    packet_dts = corrected_dts
                    PIPELINE_STATISTICS.increment("anomalous")
            if output is None:
                now = time.monotonic()
                if now < retry_at:
                    continue
                try:
                    output = av.open(
                        parameters.output_rtsp_url,
                        mode="w",
                        format="rtsp",
                        options=_rtsp_output_options(
                            parameters.output_rtsp_transport
                        ),
                    )
                    try:
                        output_stream = output.add_stream_from_template(input_stream)
                        output.start_encoding()
                    except BaseException:
                        _close_output(output)
                        output = None
                        output_stream = None
                        raise
                except Exception as error:
                    retry_at = time.monotonic() + OUTPUT_RECONNECT_INTERVAL_SECONDS
                    logger.warning(
                        "Could not open bypass RTSP output (%s); retrying in %.0f seconds: %s",
                        type(error).__name__,
                        OUTPUT_RECONNECT_INTERVAL_SECONDS,
                        error,
                    )
                    continue

            packet.stream = output_stream
            packet_details = (
                f"codec={codec_context.name!r}, size={packet.size}, "
                f"pts={packet.pts}, dts={packet_dts}, duration={packet.duration}, "
                f"packet_time_base={packet_time_base}, "
                f"output_time_base={output_stream.time_base}, "
                f"keyframe={packet.is_keyframe}, previous_dts={last_dts}"
            )
            try:
                output.mux(packet)
            except Exception as error:
                logger.warning(
                    "Bypass RTSP mux failed (%s; %s): %s",
                    packet_details,
                    type(error).__name__,
                    error,
                )
                _close_output(output)
                output = None
                output_stream = None
                retry_at = time.monotonic() + OUTPUT_RECONNECT_INTERVAL_SECONDS
                continue
            PIPELINE_STATISTICS.increment("sent")
            last_dts = (packet_dts, packet_time_base)
    finally:
        _close_output(output)


def send(
    parameters: PipelineArguments, encoded_frames: Iterator[EncodedPacket]
) -> None:
    packets = iter(encoded_frames)
    first = next(packets, None)
    if first is None:
        return

    output = None
    stream = None
    active_configuration = None
    pts = 0
    pts_increment = None
    retry_at = 0.0

    def open_output(packet: EncodedPacket):
        if packet.codec is None:
            raise ValueError("EncodedPacket must include the output codec")
        if packet.width is None or packet.height is None:
            raise ValueError("EncodedPacket must include encoded video width and height")
        if packet.time_base is None:
            raise ValueError("EncodedPacket must include the output time base")

        container = av.open(
            parameters.output_rtsp_url,
            mode="w",
            format="rtsp",
            options=_rtsp_output_options(parameters.output_rtsp_transport),
        )
        try:
            output_stream = container.add_stream(packet.codec, rate=parameters.fps)
            output_stream.width = packet.width
            output_stream.height = packet.height
            output_stream.time_base = packet.time_base
            container.start_encoding()
            return container, output_stream
        except BaseException:
            _close_output(container)
            raise

    try:
        for encoded_packet in chain((first,), packets):
            configuration = (
                encoded_packet.codec,
                encoded_packet.width,
                encoded_packet.height,
                encoded_packet.time_base,
            )
            if configuration != active_configuration:
                _close_output(output)
                output = None
                stream = None
                active_configuration = configuration
                pts = 0
                pts_increment = _pts_increment(
                    encoded_packet.time_base, parameters.fps
                )

            if output is None:
                now = time.monotonic()
                if now < retry_at:
                    pts = (pts + pts_increment) % PTS_MODULUS
                    continue
                try:
                    output, stream = open_output(encoded_packet)
                except Exception as error:
                    retry_at = time.monotonic() + OUTPUT_RECONNECT_INTERVAL_SECONDS
                    logger.warning(
                        "Could not open RTSP output (%s); retrying in %.0f seconds: %s",
                        type(error).__name__,
                        OUTPUT_RECONNECT_INTERVAL_SECONDS,
                        error,
                    )
                    pts = (pts + pts_increment) % PTS_MODULUS
                    continue

            packet = av.Packet(encoded_packet.data)
            packet.pts = pts
            packet.dts = pts
            packet.time_base = encoded_packet.time_base
            packet.stream = stream
            try:
                output.mux(packet)
            except Exception as error:
                logger.warning(
                    "RTSP mux failed (%s); reconnecting output: %s",
                    type(error).__name__,
                    error,
                )
                _close_output(output)
                output = None
                stream = None
                retry_at = time.monotonic() + OUTPUT_RECONNECT_INTERVAL_SECONDS
                pts = (pts + pts_increment) % PTS_MODULUS
                continue
            PIPELINE_STATISTICS.increment("sent")
            pts = (pts + pts_increment) % PTS_MODULUS
    finally:
        _close_output(output)
