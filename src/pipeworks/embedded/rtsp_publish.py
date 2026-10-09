import logging
import math
import time
import av
from pipeworks.embedded.stream_report import record_publish, record_stage
from typing import Iterator
from types import SimpleNamespace
from pipeworks.models import PipelineContext, Step

logger = logging.getLogger(__name__)


class RTSPPublish(Step):
    def __init__(self, url: str) -> None:
        self.url = url

    def configure(self, config: SimpleNamespace) -> None:
        if hasattr(config, "reconnect_interval"):
            raise ValueError("reconnect_interval 대신 밀리초 단위의 reconnect_interval_ms를 사용하세요.")
        reconnect_interval_ms = getattr(config, "reconnect_interval_ms", 3000)
        if (
            isinstance(reconnect_interval_ms, bool)
            or not isinstance(reconnect_interval_ms, (int, float))
            or not math.isfinite(reconnect_interval_ms)
            or reconnect_interval_ms < 0
        ):
            raise ValueError("reconnect_interval_ms는 0 이상의 유한한 숫자여야 합니다.")
        if hasattr(config, "timeout"):
            raise ValueError("timeout 대신 밀리초 단위의 timeout_ms를 사용하세요.")
        timeout_ms = getattr(config, "timeout_ms", 5000)
        if (
            isinstance(timeout_ms, bool)
            or not isinstance(timeout_ms, (int, float))
            or not math.isfinite(timeout_ms)
            or timeout_ms < 0
        ):
            raise ValueError("timeout_ms는 0 이상의 유한한 숫자여야 합니다.")

        self.reconnect = getattr(config, "reconnect", True)
        self.reconnect_interval_ms = reconnect_interval_ms
        self.transport = getattr(config, "transport", "tcp")
        self.timeout_ms = timeout_ms
        self.packet_size = getattr(config, "packet_size", 1452)

        if not isinstance(self.reconnect, bool):
            logger.error("RTSP 입력 설정에 잘못된 reconnect 값이 있습니다.")

        if self.transport not in ["tcp", "udp"]:
            logger.error("RTSP 입력 설정에 잘못된 transport 값이 있습니다.")

        if self.packet_size <= 0:
            logger.error("RTSP 입력 설정에 잘못된 packet_size 값이 있습니다.")

    def process(self, inputs: Iterator[PipelineContext]) -> Iterator[PipelineContext]:
        from fractions import Fraction
        from math import floor

        output = None
        output_stream = None
        active_stream = None
        last_dts = None
        retry_at = 0.0

        try:
            for input in inputs:
                video_stream = getattr(input, "video_stream", None)
                packet = getattr(input, "packet", None)
                if packet is None or video_stream is None:
                    raise ValueError("RTSP 송출 입력에 패킷과 비디오 스트림이 필요합니다.")

                codec = video_stream.codec_context
                stream_key = (
                    getattr(video_stream, "index", None),
                    codec.name,
                    video_stream.width,
                    video_stream.height,
                    bytes(codec.extradata or b""),
                    video_stream.time_base,
                )

                if stream_key != active_stream:
                    if output is not None:
                        try:
                            output.close()
                        except Exception:
                            logger.exception("RTSP 출력 연결을 닫지 못했습니다.")
                    output = None
                    output_stream = None
                    active_stream = stream_key
                    last_dts = None

                if output is None:
                    if time.monotonic() < retry_at:
                        continue
                    try:
                        output = av.open(
                            self.url,
                            mode="w",
                            format="rtsp",
                            options={
                                "rtsp_transport": self.transport,
                                "pkt_size": str(self.packet_size),
                                "timeout": str(int(self.timeout_ms * 1000)),
                            },
                        )
                        output_stream = output.add_stream_from_template(video_stream)
                        output.start_encoding()
                    except Exception as error:
                        record_publish(False)
                        if output is not None:
                            try:
                                output.close()
                            except Exception:
                                logger.exception("RTSP 출력 연결을 닫지 못했습니다.")
                        output = None
                        output_stream = None
                        if not self.reconnect:
                            raise
                        retry_at = time.monotonic() + self.reconnect_interval_ms / 1000
                        logger.warning("RTSP 출력 연결 실패, 재시도 예정: %s", error)
                        continue

                packet_time_base = packet.time_base or video_stream.time_base or output_stream.time_base
                if packet_time_base is None:
                    raise ValueError("RTSP 패킷에 time_base가 없습니다.")
                packet_time_base = Fraction(packet_time_base)
                if packet_time_base <= 0:
                    raise ValueError("RTSP 패킷의 time_base는 양수여야 합니다.")
                if packet.time_base is None:
                    packet.time_base = packet_time_base

                dts = packet.dts
                if dts is None:
                    if packet.pts is not None:
                        dts = packet.pts
                    elif last_dts is not None:
                        previous_dts, previous_base = last_dts
                        duration = packet.duration if packet.duration and packet.duration > 0 else 1
                        dts = floor(Fraction(previous_dts) * previous_base / packet_time_base) + duration
                    else:
                        dts = 0
                    packet.dts = dts
                if last_dts is not None:
                    previous_dts, previous_base = last_dts
                    if Fraction(dts) * packet_time_base <= Fraction(previous_dts) * previous_base:
                        duration = packet.duration if packet.duration and packet.duration > 0 else 1
                        corrected = floor(Fraction(previous_dts) * previous_base / packet_time_base) + duration
                        if packet.pts is not None:
                            packet.pts += corrected - dts
                        packet.dts = dts = corrected
                packet.stream = output_stream

                try:
                    publish_started_at = time.perf_counter()
                    output.mux(packet)
                    record_publish(True)
                    record_stage("publish", time.perf_counter() - publish_started_at)
                except Exception as error:
                    record_publish(False)
                    try:
                        output.close()
                    except Exception:
                        logger.exception("RTSP 출력 연결을 닫지 못했습니다.")
                    output = None
                    output_stream = None
                    if not self.reconnect:
                        raise
                    retry_at = time.monotonic() + self.reconnect_interval_ms / 1000
                    logger.warning("RTSP 패킷 송신 실패, 재시도 예정: %s", error)
                    continue

                last_dts = (dts, packet_time_base)
        finally:
            if output is not None:
                try:
                    output.close()
                except Exception:
                    logger.exception("RTSP 출력 연결을 닫지 못했습니다.")

        yield from ()
