"""RTSP 입력에서 비디오 패킷을 순서대로 수신한다."""

import logging
import time
from collections.abc import Iterator
from threading import Event

import av

from pipeline.context import ReceivePacket
from pipeline.arguments import PipelineArguments
from pipeline.statistics import PIPELINE_STATISTICS

logger = logging.getLogger(__name__)
RECONNECT_INTERVAL_SECONDS = 3.0


def receive(
    parameters: PipelineArguments, stop_event: Event | None = None
) -> Iterator[ReceivePacket]:
    """입력 RTSP의 첫 비디오 스트림에서 패킷을 반환하고 끊기면 재연결한다.

    각 패킷은 해당 스트림의 codec context와 PyAV Packet을 보존한다.
    연결 또는 읽기가 실패하거나 스트림이 끝나면 컨테이너를 닫고 3초 뒤 재시도한다.
    iterator가 닫히면 재시도를 중단하고 현재 입력 컨테이너를 닫는다.
    """

    while stop_event is None or not stop_event.is_set():
        container = None
        try:
            container = av.open(
                parameters.input_rtsp_url,
                mode="r",
                options={"rtsp_transport": parameters.input_rtsp_transport},
                timeout=(5.0, 5.0),
            )

            video_streams = container.streams.video
            if not video_streams:
                raise RuntimeError("RTSP 입력에 비디오 스트림이 없습니다.")

            video_stream = video_streams[0]
            for packet in container.demux(video_stream):
                if stop_event is not None and stop_event.is_set():
                    break
                if packet.size <= 0:
                    continue
                PIPELINE_STATISTICS.increment("received")
                yield ReceivePacket(video_stream=video_stream, data=packet)

            if stop_event is not None and stop_event.is_set():
                break

            logger.warning(
                "RTSP 입력 스트림이 종료되었습니다. %.0f초 후 재연결을 시도합니다.",
                RECONNECT_INTERVAL_SECONDS,
            )
        except av.error.FFmpegError:
            logger.warning(
                "RTSP 입력 연결 또는 패킷 수신에 실패했습니다. %.0f초 후 재연결을 시도합니다.",
                RECONNECT_INTERVAL_SECONDS,
            )
        finally:
            if container is not None:
                try:
                    container.close()
                except av.error.FFmpegError:
                    logger.error(
                        "RTSP 입력 컨테이너 정리 중 FFmpeg 오류가 발생했습니다."
                    )

        if stop_event is None:
            time.sleep(RECONNECT_INTERVAL_SECONDS)
        elif not stop_event.wait(RECONNECT_INTERVAL_SECONDS):
            continue
