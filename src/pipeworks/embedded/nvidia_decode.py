"""수신·디코딩을 독립 실행하고 최대 30개 프레임을 FIFO로 전달한다."""

from contextvars import copy_context
from collections import deque
import logging
from threading import Condition, Event, Thread
import time
from types import SimpleNamespace
from typing import Iterator

import torch

from pipeworks.execution import _source_cancel_scope
from pipeworks.models import PipelineContext, Step


logger = logging.getLogger(__name__)


class _LockedBuffer:
    """CUDA Array Interface owner retained by the shared Tensor storage."""

    def __init__(self, pool, pointer, ready):
        self.pool, self.pointer, self.completion = pool, pointer, ready
        self.ready = ready
        self.__cuda_array_interface__ = {
            "version": 3, "shape": pool.shape, "strides": pool.strides,
            "typestr": pool.typestr, "data": (pointer, False),
        }

    def __del__(self):
        try:
            self.pool.retire(self.pointer, self.completion)
        except Exception:
            logger.exception("디코더 잠금 버퍼 반환에 실패했습니다.")


class _DecoderBuffers:
    """Keep native output locks until both GPU work and shared owners finish."""

    limit = 34

    def __init__(self, decoder, stream, pixel_format):
        self.decoder, self.stream = decoder, stream
        self.condition = Condition()
        self.locked = set()
        self.retired = []
        self.closed = False
        width, height, size = decoder.GetWidth(), decoder.GetHeight(), decoder.GetFrameSize()
        name = getattr(pixel_format, "name", str(pixel_format)).upper()
        layouts = {"NV12": (height * 3 // 2, "|u1", 1),
                   "P016": (height * 3 // 2, "<u2", 2),
                   "NV16": (height * 2, "|u1", 1),
                   "P216": (height * 2, "<u2", 2),
                   "YUV444": (height * 3, "|u1", 1),
                   "YUV444_16BIT": (height * 3, "<u2", 2)}
        if name not in layouts:
            raise ValueError(f"무복사 디코딩에서 지원하지 않는 픽셀 형식: {name}")
        rows, self.typestr, element_size = layouts[name]
        pitch, remainder = divmod(size, rows)
        if remainder or pitch < width * element_size or pitch % element_size:
            raise ValueError("디코더 출력 크기와 픽셀 레이아웃이 일치하지 않습니다.")
        self.shape, self.strides = (rows, width), (pitch, element_size)

    def retire(self, pointer, event):
        with self.condition:
            if self.closed:
                # After producer shutdown, the last external Tensor may outlive process().
                event.synchronize()
                self.decoder.UnlockFrame(pointer)
                self.locked.remove(pointer)
            else:
                self.retired.append((pointer, event))
            self.condition.notify_all()

    def reap(self, *, wait=False):
        with self.condition:
            remaining = []
            for pointer, event in self.retired:
                if wait:
                    event.synchronize()
                elif not event.query():
                    remaining.append((pointer, event))
                    continue
                self.decoder.UnlockFrame(pointer)
                self.locked.remove(pointer)
            self.retired = remaining
            self.condition.notify_all()

    def available(self, stopped):
        while not stopped():
            self.reap()
            with self.condition:
                if len(self.locked) < self.limit:
                    return True
                self.condition.wait(.001)
        return False

    def acquire(self):
        pointer = self.decoder.GetLockedFrame()
        ready = torch.cuda.Event()
        ready.record(self.stream)
        with self.condition:
            if pointer in self.locked:
                raise RuntimeError("디코더가 이미 잠긴 버퍼를 다시 반환했습니다.")
            self.locked.add(pointer)
        owner = _LockedBuffer(self, pointer, ready)
        # as_tensor retains owner; DLPack aliases retain the same Tensor storage.
        with torch.cuda.stream(self.stream):
            frame = torch.as_tensor(owner, device=self.stream.device)
        return frame, owner

    def close(self):
        with self.condition:
            self.closed = True
            self.reap(wait=True)


class _FrameQueue:
    capacity = 30

    def __init__(self):
        self.condition = Condition()
        self.pending = deque()
        self.finished = False
        self.cancelled = False
        self.error = None
        self.dropped = 0
        self.buffers = None

    def make_room(self):
        with self.condition:
            if len(self.pending) >= self.capacity:
                self.pending.popleft()
                self.dropped += 1

    def publish(self, item):
        with self.condition:
            if self.cancelled:
                return
            self.make_room()
            self.pending.append(item)
            self.condition.notify_all()

    def take(self, stop=None):
        with self.condition:
            while True:
                if self.cancelled or (stop is not None and stop.is_set()):
                    return None
                if self.error is not None:
                    raise self.error
                if self.pending:
                    item = self.pending.popleft()
                    item.decode_dropped_frames = self.dropped
                    return item
                if self.finished:
                    return None
                self.condition.wait(.1)

    def finish(self, error=None):
        with self.condition:
            self.finished = True
            self.error = error
            self.condition.notify_all()

    def cancel(self):
        with self.condition:
            self.cancelled = True
            self.pending.clear()
            self.condition.notify_all()


class NvidiaDecode(Step):
    def configure(self, config: SimpleNamespace) -> None:
        self.gpu_id = getattr(config, "gpu_id", 0)

    def _produce(self, inputs, slot, cancel):
        import PyNvVideoCodec as nvc

        decoder = None
        decode_stream = consumer_stream = video_stream = pixel_format = None
        stop = getattr(self, "_pipeworks_stop_event", None)

        def stopped():
            return cancel.is_set() or (stop is not None and stop.is_set())

        def publish(frames):
            if not frames or stopped():
                return
            for frame in frames:
                if callable(getattr(frame, "__dlpack__", None)):
                    raise RuntimeError("GPU 디코딩에는 GetLockedFrame 잠금 API가 필요합니다.")
                slot.publish(PipelineContext(
                    frame=frame, video_stream=video_stream, cuda_stream=consumer_stream,
                    pixel_format=pixel_format, decoded_at=time.perf_counter(),
                ))

        def decode(packet_data):
            nonlocal pixel_format
            if not locked_decoder:
                publish(decoder.Decode(packet_data))
                return
            count = decoder.GetNumDecodedFrame(packet_data)
            if not count:
                return
            if slot.buffers is None:
                pixel_format = decoder.GetPixelFormat()
                slot.buffers = _DecoderBuffers(decoder, decode_stream, pixel_format)
            buffers = slot.buffers
            for _ in range(count):
                slot.make_room()
                if not buffers.available(stopped):
                    return
                frame, owner = buffers.acquire()
                slot.publish(PipelineContext(
                    frame=frame, _decode_buffer=owner, video_stream=video_stream,
                    cuda_stream=consumer_stream, pixel_format=pixel_format,
                    decoded_at=time.perf_counter(),
                ))
                del frame, owner
            buffers.reap()

        for item in inputs:
            if stopped():
                return
            if decoder is None:
                video_stream = item.video_stream
                codec_ids = {"h264": nvc.cudaVideoCodec.H264,
                             "hevc": nvc.cudaVideoCodec.HEVC, "h265": nvc.cudaVideoCodec.HEVC}
                decode_stream = torch.cuda.Stream(device=self.gpu_id)
                consumer_stream = torch.cuda.Stream(device=self.gpu_id)
                decoder = nvc.CreateDecoder(
                    gpuid=self.gpu_id, codec=codec_ids[video_stream.codec.name.lower()],
                    usedevicememory=True, outputColorType=nvc.OutputColorType.NATIVE,
                    latency=nvc.DisplayDecodeLatencyType.NATIVE, cudastream=decode_stream.cuda_stream,
                )
                pixel_format = decoder.GetPixelFormat()
                if all(callable(getattr(decoder, name, None)) for name in
                       ("GetNumDecodedFrame", "GetLockedFrame", "UnlockFrame")):
                    # Geometry becomes available after the first packet is decoded.
                    locked_decoder = True
                else:
                    locked_decoder = False
            packet_data = nvc.PacketData()
            # Keep the packet owner alive until the decoder has consumed its bitstream.
            packet = item.packet
            packet_data.bsl_data = packet.buffer_ptr
            packet_data.bsl = packet.size
            if packet.pts is not None:
                packet_data.pts = int(packet.pts)
            with torch.cuda.stream(decode_stream):
                decode(packet_data)
            del item, packet

        if decoder is not None and not stopped():
            with torch.cuda.stream(decode_stream):
                if locked_decoder:
                    decode(nvc.PacketData())
                else:
                    publish(decoder.Flush())

    def process(self, inputs: Iterator[PipelineContext]) -> Iterator[PipelineContext]:
        from pipeworks.main import _current_output_writer, _use_output_writer

        inputs = iter(inputs)
        slot, cancel = _FrameQueue(), Event()
        context = copy_context()
        output_writer = _current_output_writer()

        def produce():
            error = None
            try:
                with _use_output_writer(output_writer), _source_cancel_scope(cancel):
                    self._produce(inputs, slot, cancel)
            except BaseException as caught:
                error = caught
            finally:
                if cancel.is_set() or error is not None:
                    close = getattr(inputs, "close", None)
                    if callable(close):
                        try:
                            close()
                        except BaseException as caught:
                            if error is None:
                                error = caught
                slot.finish(error)

        worker = Thread(target=lambda: context.run(produce), name="pipeworks-nvidia-decode", daemon=True)
        worker.start()
        try:
            while True:
                item = slot.take(getattr(self, "_pipeworks_stop_event", None))
                if item is None:
                    return
                stream = item.cuda_stream
                owner = getattr(item, "_decode_buffer", None)
                if owner is not None:
                    stream.wait_event(owner.ready)
                item.processing_started_at = time.perf_counter()
                with torch.cuda.stream(stream):
                    try:
                        yield item
                    finally:
                        if owner is not None:
                            done = torch.cuda.Event()
                            done.record(stream)
                            owner.completion = done
                del item, owner
        finally:
            cancel.set()
            slot.cancel()
            # 소스 읽기 중이면 기존 RTSP 제한 시간/다음 패킷까지 기다린다.
            worker.join()
            # External Tensor aliases keep their locks until their last reference ends.
            item = owner = None
            if slot.buffers is not None:
                slot.buffers.close()
