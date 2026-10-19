from typing import Iterator
from types import SimpleNamespace
from fractions import Fraction
import logging
from pipeworks.embedded.recovery import is_fatal, gpu_call
import time

import av
import torch
from pipeworks.models import PipelineContext, Step
from pipeworks.video import CodecInfo, encoded_stream_info
from pipeworks.embedded.stream_report import record_frame, record_stage


logger = logging.getLogger(__name__)


class _EncodeError(Exception):
    pass


class NvidiaEncode(Step):
    def __init__(self, *, gpu_id: int = 0, fps: float = 30) -> None:
        self._set_config_defaults(gpu_id=gpu_id, fps=fps)

    def configure(self, config: SimpleNamespace) -> None:
        config = self._resolve_config(config)
        self.gpu_id = getattr(config, "gpu_id", 0)
        self.fps = getattr(config, "fps", 30)
        if self.fps <= 0:
            raise ValueError("NVIDIA 인코딩 fps는 양수여야 합니다.")

    def process(self, inputs: Iterator[PipelineContext]) -> Iterator[PipelineContext]:
        import PyNvVideoCodec as nvc

        encoder = None
        video_stream = None
        output_info = codec_info = None
        cuda_stream = None
        last_input = None
        fps, gpu_id = self.fps, self.gpu_id
        time_base = Fraction(1, fps)
        next_pts = 0
        active_key = None
        retry_at = 0.0
        recovering = False
        cleanup_failed = False
        stop = getattr(self, "_pipeworks_stop_event", None)
        native_errors = (RuntimeError,)
        if isinstance(getattr(nvc, "PyNvVCException", None), type):
            native_errors += (nvc.PyNvVCException,)

        def native_call(method, *args, **kwargs):
            try:
                return method(*args, **kwargs)
            except native_errors as error:
                if is_fatal(error):
                    raise
                message = str(error)
            # 복구 예외가 bound method·원본 traceback·프레임을 붙잡지 않게 한다.
            method, args, kwargs = None, (), None
            raise _EncodeError(message)

        def release():
            nonlocal encoder, cuda_stream, last_input, cleanup_failed
            if cleanup_failed:
                return
            try:
                if cuda_stream is not None:
                    gpu_call(cuda_stream.synchronize)
            except BaseException:
                cleanup_failed = True
                raise
            encoder = None
            last_input = None
            cuda_stream = None

        def stopped():
            return stop is not None and stop.is_set()

        def output_packet(encoded_packets: object) -> Iterator[PipelineContext]:
            nonlocal next_pts, recovering, output_info
            if encoded_packets is None:
                return
            if isinstance(encoded_packets, (bytes, bytearray, memoryview, dict)):
                encoded_packets = (encoded_packets,)
            elif isinstance(encoded_packets, (list, tuple)) and all(
                isinstance(value, int) for value in encoded_packets
            ):
                encoded_packets = (encoded_packets,)

            try:
                packets = iter(encoded_packets)
            except Exception as error:
                if is_fatal(error):
                    raise
                logger.warning("잘못된 인코더 출력 묶음을 버립니다: %s", error)
                return
            while True:
                try:
                    encoded_packet = next(packets)
                except StopIteration:
                    return
                except Exception as error:
                    if is_fatal(error):
                        raise
                    logger.warning("인코더 출력 읽기 실패로 나머지 패킷을 버립니다: %s", error)
                    return
                try:
                    data = encoded_bytes(encoded_packet)
                except Exception as error:
                    if is_fatal(error):
                        raise
                    logger.warning("잘못된 인코더 패킷을 버립니다: %s", error)
                    continue
                if not data:
                    continue

                try:
                    if output_info is None:
                        output_info = encoded_stream_info(codec_info, data, time_base)

                    packet = av.Packet(data)
                    packet.pts = next_pts
                    packet.dts = next_pts
                    packet.time_base = time_base
                    packet.duration = 1
                    next_pts += 1
                except Exception as error:
                    if is_fatal(error):
                        raise
                    logger.warning("인코더 출력 패킷 생성 실패로 폐기합니다: %s", error)
                    continue
                if recovering:
                    logger.info("인코더 복구 후 영상 출력을 재개했습니다.")
                    recovering = False
                yield PipelineContext(packet=packet, video_stream=output_info)

        def flush():
            try:
                with torch.cuda.stream(cuda_stream):
                    packets = native_call(encoder.EndEncode)
            except Exception as error:
                if is_fatal(error):
                    raise
                logger.warning("인코더 종료 처리 오류로 지연 패킷을 버립니다: %s", error)
                return
            yield from output_packet(packets)

        try:
            for input in inputs:
                if stopped():
                    return
                try:
                    codec = input.video_stream.codec_context
                    pixel_format = getattr(input.pixel_format, "name", input.pixel_format)
                    stream_key = (
                        codec.name.lower(), codec.width, codec.height,
                        pixel_format, input.cuda_stream.cuda_stream,
                    )
                    if not codec.name or codec.width <= 0 or codec.height <= 0:
                        raise ValueError("인코더 코덱 이름과 양수 크기가 필요합니다.")
                except Exception as error:
                    if is_fatal(error):
                        raise
                    logger.warning("잘못된 인코딩 입력을 버립니다: %s", error)
                    continue
                if encoder is not None and (
                    input.video_stream is not video_stream or stream_key != active_key
                ):
                    logger.warning("입력 스트림 또는 영상 형식이 변경되어 인코더를 재생성합니다.")
                    # 기존 세대의 지연 출력은 기존 메타데이터로 전달한다.
                    yield from flush()
                    release()
                    recovering = True
                if encoder is None and time.monotonic() < retry_at:
                    continue
                try:
                    if encoder is None:
                        video_stream = input.video_stream
                        cuda_stream = input.cuda_stream
                        encoder_kwargs = {
                            "gpu_id": gpu_id,
                            "codec": stream_key[0],
                            "bf": 0,
                            "fps": fps,
                            "gop": fps,
                            "idrperiod": fps,
                            "cudastream": cuda_stream.cuda_stream,
                        }
                        if stream_key[0] in ("h264", "hevc", "h265"):
                            encoder_kwargs["repeatspspps"] = 1
                        encoder = native_call(
                            nvc.CreateEncoder,
                            codec.width, codec.height, pixel_format, False,
                            **encoder_kwargs,
                        )
                        codec_info = CodecInfo(
                            stream_key[0], codec.width, codec.height,
                            pix_fmt={
                                "NV12": "yuv420p", "P010": "yuv420p10le",
                                "YUV444": "yuv444p", "YUV444_16Bit": "yuv444p10le",
                            }.get(pixel_format),
                        )
                        output_info = None
                        active_key = stream_key
                    encode_started_at = time.perf_counter()
                    last_input = input
                    with torch.cuda.stream(input.cuda_stream):
                        encoded_packets = native_call(encoder.Encode, input.frame)
                except Exception as error:
                    if is_fatal(error):
                        raise
                    logger.warning(
                        "인코더 오류로 자동 복구를 시도합니다. 1초 후 새 프레임에서 재시도합니다: %s",
                        error,
                    )
                    release()
                    retry_at = time.monotonic() + 1.0
                    recovering = True
                    continue
                try:
                    record_stage("encode", time.perf_counter() - encode_started_at)
                    started_at = getattr(input, "processing_started_at", None)
                    if started_at is not None:
                        record_frame(time.perf_counter() - started_at)
                except Exception as error:
                    if is_fatal(error):
                        raise
                    logger.warning("인코딩 보고 실패: %s", error)
                yield from output_packet(encoded_packets)

            if encoder is not None and not stopped():
                yield from flush()
        finally:
            # 마지막 제출 입력과 스트림은 GPU 작업 및 인코더 해제까지 유지한다.
            release()


def encoded_bytes(encoded: object) -> bytes:
    if isinstance(encoded, (bytes, bytearray, memoryview)):
        return bytes(encoded)
    if isinstance(encoded, dict):
        for key in ("bitstream", "data", "packet", "encoded_data", "payload"):
            if key in encoded:
                try:
                    return encoded_bytes(encoded[key])
                except TypeError:
                    pass
        for value in encoded.values():
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
