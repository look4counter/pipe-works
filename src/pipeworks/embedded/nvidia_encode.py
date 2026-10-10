from typing import Iterator
from types import SimpleNamespace
from fractions import Fraction
import time

import av
import torch
from pipeworks.models import PipelineContext, Step
from pipeworks.embedded.stream_report import record_frame, record_stage


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
        cuda_stream = None
        time_base = Fraction(1, self.fps)
        next_pts = 0

        def output_packet(encoded_packets: object) -> Iterator[PipelineContext]:
            nonlocal next_pts
            if encoded_packets is None:
                return
            if isinstance(encoded_packets, (bytes, bytearray, memoryview, dict)):
                encoded_packets = (encoded_packets,)
            elif isinstance(encoded_packets, (list, tuple)) and all(
                isinstance(value, int) for value in encoded_packets
            ):
                encoded_packets = (encoded_packets,)

            for encoded_packet in encoded_packets:
                data = encoded_bytes(encoded_packet)
                if not data:
                    continue

                packet = av.Packet(data)
                packet.pts = next_pts
                packet.dts = next_pts
                packet.time_base = time_base
                packet.duration = 1
                next_pts += 1
                yield PipelineContext(packet=packet, video_stream=video_stream)

        for input in inputs:
            if encoder is None:
                video_stream = input.video_stream
                cuda_stream = input.cuda_stream

                encoder_kwargs = {
                    "gpu_id": self.gpu_id,
                    "codec": video_stream.codec_context.name.lower(),
                    "bf": 0,
                    "fps": self.fps,
                    "gop": self.fps,
                    "idrperiod": self.fps,
                    "cudastream": cuda_stream.cuda_stream,
                }

                encoder = nvc.CreateEncoder(
                    video_stream.codec_context.width,
                    video_stream.codec_context.height,
                    getattr(input.pixel_format, "name", input.pixel_format),
                    False,
                    **encoder_kwargs,
                )

            encode_started_at = time.perf_counter()
            with torch.cuda.stream(input.cuda_stream):
                encoded_packets = encoder.Encode(input.frame)
            record_stage("encode", time.perf_counter() - encode_started_at)

            started_at = getattr(input, "processing_started_at", None)
            if started_at is not None:
                record_frame(time.perf_counter() - started_at)

            yield from output_packet(encoded_packets)

        if encoder is not None:
            with torch.cuda.stream(cuda_stream):
                encoded_packets = encoder.EndEncode()
            yield from output_packet(encoded_packets)


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
