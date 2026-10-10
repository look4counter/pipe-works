import logging
import math
import time
import av
from pipeworks.embedded.stream_report import record_receive
from typing import Iterator
from types import SimpleNamespace
from pipeworks.models import PipelineContext, Step
from pipeworks.execution import current_source_cancel

logger = logging.getLogger(__name__)


class RTSPSource(Step):
    def __init__(self, url: str, *, reconnect: bool = True,
                 reconnect_interval_ms: float = 3000, transport: str = "tcp",
                 timeout_ms: float = 5000) -> None:
        self.url = url
        self._set_config_defaults(reconnect=reconnect, reconnect_interval_ms=reconnect_interval_ms,
                                  transport=transport, timeout_ms=timeout_ms)

    def configure(self, config: SimpleNamespace) -> None:
        config = self._resolve_config(config)
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

        if not isinstance(self.reconnect, bool):
            logger.error("RTSP 입력 설정에 잘못된 reconnect 값이 있습니다.")

        if self.transport not in ["tcp", "udp"]:
            logger.error("RTSP 입력 설정에 잘못된 transport 값이 있습니다.")

    def process(self, _: Iterator[PipelineContext]) -> Iterator[PipelineContext]:
        stop = getattr(self, "_pipeworks_stop_event", None)
        cancel = current_source_cancel()
        while (stop is None or not stop.is_set()) and (cancel is None or not cancel.is_set()):
            container = None
            try:
                container = av.open(
                    self.url,
                    mode="r",
                    options={"rtsp_transport": self.transport},
                    timeout=(self.timeout_ms / 1000, self.timeout_ms / 1000),
                )
                video_streams = container.streams.video
                if not video_streams:
                    record_receive(False)
                    raise RuntimeError("RTSP 입력에 비디오 스트림이 없습니다.")

                video_stream = video_streams[0]
                for packet in container.demux(video_stream):
                    if (stop is not None and stop.is_set()) or (cancel is not None and cancel.is_set()):
                        return
                    if packet.size > 0:
                        record_receive(True)
                        yield PipelineContext(video_stream=video_stream, packet=packet)

                record_receive(False)
                if not self.reconnect:
                    raise RuntimeError("RTSP 입력 스트림이 종료되어 파이프라인 실행을 중단합니다.")
                logger.warning(
                    "RTSP 입력 스트림이 종료되었습니다. %gms 후 재연결을 시도합니다.",
                    self.reconnect_interval_ms,
                )
            except av.error.FFmpegError as error:
                record_receive(False)
                if self.reconnect:
                    logger.warning(
                        "RTSP 입력 연결 또는 패킷 수신에 실패했습니다. %gms 후 재연결을 시도합니다.",
                        self.reconnect_interval_ms,
                    )
                else:
                    raise RuntimeError(
                        "RTSP 입력 연결 또는 패킷 수신에 실패하여 파이프라인 실행을 중단합니다."
                    ) from error
            finally:
                if container is not None:
                    try:
                        container.close()
                    except av.error.FFmpegError:
                        logger.error(
                            "RTSP 입력 컨테이너 정리 중 FFmpeg 오류가 발생했습니다."
                        )

            if cancel is not None:
                deadline = time.monotonic() + self.reconnect_interval_ms / 1000
                while not cancel.is_set() and (stop is None or not stop.is_set()):
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    cancel.wait(min(.1, remaining))
            elif stop is not None:
                stop.wait(self.reconnect_interval_ms / 1000)
            else:
                time.sleep(self.reconnect_interval_ms / 1000)
