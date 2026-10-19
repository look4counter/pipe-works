
from dataclasses import dataclass, field
from fractions import Fraction
from io import BytesIO
import re
from uuid import uuid4

from av import open as open_container


@dataclass(frozen=True, slots=True)
class CodecInfo:
    name: str
    width: int
    height: int
    extradata: bytes = b""
    pix_fmt: str | None = None

    def __post_init__(self):
        object.__setattr__(self, "extradata", bytes(self.extradata or b""))


@dataclass(frozen=True, slots=True)
class VideoStreamInfo:
    codec_context: CodecInfo
    time_base: Fraction | None = None
    average_rate: Fraction | None = None
    index: int = 0
    connection_id: str = field(default_factory=lambda: uuid4().hex)

    @property
    def codec(self) -> CodecInfo:
        return self.codec_context

    @property
    def width(self) -> int:
        return self.codec_context.width

    @property
    def height(self) -> int:
        return self.codec_context.height

    @classmethod
    def from_stream(cls, stream) -> "VideoStreamInfo":
        codec = stream.codec_context
        return cls(
            CodecInfo(
                str(codec.name), int(codec.width), int(codec.height),
                bytes(codec.extradata or b""), getattr(codec, "pix_fmt", None),
            ),
            _fraction(stream.time_base),
            _fraction(getattr(stream, "average_rate", None)),
            int(stream.index),
        )

    def add_to_output(self, output):
        codec = self.codec_context
        # add_mux_stream은 extradata를 설정할 수 없다. 빈 로컬 템플릿으로
        # remux 상태만 초기화한 뒤 출력 소유 코덱에 독립 값들을 넣는다.
        with open_container(BytesIO(), mode="w", format="matroska") as temporary:
            template = temporary.add_stream(codec.name)
            stream = output.add_stream_from_template(template, opaque=True)
            context = stream.codec_context
            context.width = codec.width
            context.height = codec.height
            if codec.pix_fmt is not None:
                context.pix_fmt = codec.pix_fmt
            context.extradata = codec.extradata
            if self.time_base is not None:
                stream.time_base = self.time_base
            if self.average_rate is not None:
                context.framerate = self.average_rate
        return stream


def _fraction(value):
    return Fraction(value) if value is not None else None


def encoded_stream_info(source, data: bytes, time_base: Fraction) -> VideoStreamInfo:
    codec = getattr(source, "codec_context", source)
    name = codec.name.lower()
    name = "hevc" if name == "h265" else name
    headers = []
    for nal in re.split(b"\x00\x00\x00?\x01", data)[1:]:
        if not nal:
            continue
        kind = nal[0] & 0x1F if name == "h264" else (nal[0] >> 1) & 0x3F
        if kind in ((7, 8) if name == "h264" else (32, 33, 34)):
            headers.append(b"\x00\x00\x00\x01" + nal)
    return VideoStreamInfo(
        CodecInfo(name, codec.width, codec.height, b"".join(headers),
                  getattr(codec, "pix_fmt", None)),
        time_base, 1 / time_base,
    )
