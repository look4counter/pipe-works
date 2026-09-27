from dataclasses import dataclass
from av import VideoStream
from fractions import Fraction


@dataclass(slots=True)
class ReceivePacket:
    video_stream: VideoStream
    data: object
    cuda_stream: object | None = None


@dataclass(slots=True)
class FrameContext:
    video_stream: VideoStream
    # Stage adapters may wrap the payload for inference and encoding.
    data: object
    cuda_stream: object | None = None
    pixel_format: str | None = None
    codec: str | None = None
    width: int | None = None
    height: int | None = None
    inference_result: object | None = None
    metadata: object | None = None
    decode_started_at_ns: int | None = None
    # Retain the native decoder object for encoders requiring its CUDA interface.
    encoder_data: object | None = None


@dataclass(slots=True)
class EncodedPacket:
    video_stream: VideoStream
    data: bytes
    time_base: Fraction | None = None
    codec: str | None = None
    width: int | None = None
    height: int | None = None
