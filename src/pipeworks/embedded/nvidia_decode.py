from typing import Iterator
from types import SimpleNamespace
import time
from pipeworks.models import PipelineContext, Step
import torch
import ctypes


class NvidiaDecode(Step):

    def configure(self, config: SimpleNamespace) -> None:
        self.gpu_id = getattr(config, "gpu_id", 0)

    def process(self, inputs: Iterator[PipelineContext]) -> Iterator[PipelineContext]:
        import PyNvVideoCodec as nvc

        decoder = None

        for input in inputs:
            if decoder is None:
                video_stream = input.video_stream

                codec_ids = {
                    "h264": nvc.cudaVideoCodec.H264,
                    "hevc": nvc.cudaVideoCodec.HEVC,
                    "h265": nvc.cudaVideoCodec.HEVC,
                }

                cuda_stream = torch.cuda.Stream(device=self.gpu_id)

                decoder_kwargs = {
                    "gpuid": self.gpu_id,
                    "codec": codec_ids[video_stream.codec.name.lower()],
                    "usedevicememory": True,
                    "outputColorType": nvc.OutputColorType.NATIVE,
                    "latency": nvc.DisplayDecodeLatencyType.NATIVE,
                    "cudastream": cuda_stream.cuda_stream,
                }

                decoder = nvc.CreateDecoder(**decoder_kwargs)

                pixel_format = decoder.GetPixelFormat()

            packet_data = nvc.PacketData()
            bitstream = ctypes.create_string_buffer(bytes(input.packet))
            packet_data.bsl_data = ctypes.addressof(bitstream)
            packet_data.bsl = len(bitstream) - 1

            if input.packet.pts is not None:
                packet_data.pts = int(input.packet.pts)

            with torch.cuda.stream(cuda_stream):
                frames = decoder.Decode(packet_data)
                for frame in frames:
                    yield PipelineContext(
                        frame=frame,
                        video_stream=video_stream,
                        cuda_stream=cuda_stream,
                        pixel_format=pixel_format,
                        processing_started_at=time.perf_counter(),
                    )

        if decoder is not None:
            with torch.cuda.stream(cuda_stream):
                for frame in decoder.Flush():
                    yield PipelineContext(
                        frame=frame,
                        video_stream=video_stream,
                        cuda_stream=cuda_stream,
                        pixel_format=pixel_format,
                        processing_started_at=time.perf_counter(),
                    )
