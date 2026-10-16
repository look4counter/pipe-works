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


class _DecodeError(Exception):
    """네이티브 디코더 호출에서 발생한 복구 대상 오류."""


class _LockedBuffer:
    """CUDA Array Interface owner retained by the shared Tensor storage."""

    def __init__(self, pool, pointer, ready):
        self.pool, self.pointer, self.completion = pool, pointer, ready
        self.ready = ready
        self.__cuda_array_interface__ = {
            "version": 3,
            "shape": pool.shape,
            "strides": pool.strides,
            "typestr": pool.typestr,
            "data": (pointer, False),
        }

    def __del__(self):
        try:
            self.pool.retire(self.pointer, self.completion)
        except Exception:
            logger.exception("디코더 잠금 버퍼 반환에 실패했습니다.")


class _DecoderBuffers:
    """Keep native output locks until both GPU work and shared owners finish."""

    limit = 34

    def __init__(self, decoder, stream, pixel_format, native_call=None):
        self.decoder, self.stream = decoder, stream
        self.condition = Condition()
        self.locked = set()
        self.retired = []
        self.closed = False
        self._cleanup_failed = False
        call = native_call or (lambda method: method())
        width, height, size = (
            call(decoder.GetWidth),
            call(decoder.GetHeight),
            call(decoder.GetFrameSize),
        )
        name = getattr(pixel_format, "name", str(pixel_format)).upper()
        layouts = {
            "NV12": (height * 3 // 2, "|u1", 1),
            "P016": (height * 3 // 2, "<u2", 2),
            "NV16": (height * 2, "|u1", 1),
            "P216": (height * 2, "<u2", 2),
            "YUV444": (height * 3, "|u1", 1),
            "YUV444_16BIT": (height * 3, "<u2", 2),
        }
        if name not in layouts:
            raise ValueError(f"무복사 디코딩에서 지원하지 않는 픽셀 형식: {name}")
        rows, self.typestr, element_size = layouts[name]
        pitch, remainder = divmod(size, rows)
        if remainder or pitch < width * element_size or pitch % element_size:
            raise ValueError("디코더 출력 크기와 픽셀 레이아웃이 일치하지 않습니다.")
        self.shape, self.strides = (rows, width), (pitch, element_size)

    def retire(self, pointer, event):
        with self.condition:
            self.retired.append((pointer, event))
            if self.closed and not self._cleanup_failed:
                # 종료 후 마지막 외부 참조도 같은 정리 실패 상태를 따른다.
                self.reap(wait=True)
            self.condition.notify_all()

    def reap(self, *, wait=False):
        with self.condition:
            if self._cleanup_failed:
                return
            index = 0
            while index < len(self.retired):
                pointer, event = self.retired[index]
                try:
                    if wait:
                        event.synchronize()
                    elif not event.query():
                        index += 1
                        continue
                    self.decoder.UnlockFrame(pointer)
                    self.locked.remove(pointer)
                except BaseException:
                    # 네이티브 반환의 성공 여부가 불명확하므로 재시도하지 않는다.
                    self._cleanup_failed = True
                    raise
                # 이후 항목이 실패해도 이미 반환한 포인터는 다시 처리하지 않는다.
                del self.retired[index]
            self.condition.notify_all()

    def available(self, stopped):
        while not stopped():
            if self._cleanup_failed:
                raise RuntimeError("정리에 실패한 디코더 버퍼 풀은 재사용할 수 없습니다.")
            self.reap()
            with self.condition:
                if len(self.locked) < self.limit:
                    return True
                self.condition.wait(0.001)
        return False

    def acquire(self, native_call=None):
        if self._cleanup_failed:
            raise RuntimeError("정리에 실패한 디코더 버퍼 풀은 재사용할 수 없습니다.")
        call = native_call or (lambda method: method())
        pointer = call(self.decoder.GetLockedFrame)
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
                self.condition.wait(0.1)

    def finish(self, error=None):
        with self.condition:
            self.finished = True
            self.error = error
            self.condition.notify_all()

    def discard(self):
        with self.condition:
            self.dropped += len(self.pending)
            self.pending.clear()

    def cancel(self):
        with self.condition:
            self.cancelled = True
            self.pending.clear()
            self.condition.notify_all()


class NvidiaDecode(Step):
    def __init__(self, *, gpu_id: int = 0) -> None:
        self._set_config_defaults(gpu_id=gpu_id)

    def configure(self, config: SimpleNamespace) -> None:
        config = self._resolve_config(config)
        self.gpu_id = getattr(config, "gpu_id", 0)

    def _produce(self, inputs, slot, cancel):
        import PyNvVideoCodec as nvc

        decoder = None
        decode_stream = consumer_stream = video_stream = pixel_format = None
        stop = getattr(self, "_pipeworks_stop_event", None)
        waiting_keyframe = recovering = False
        cleanup_failed = False
        native_errors = (RuntimeError,)
        if isinstance(getattr(nvc, "PyNvVCException", None), type):
            native_errors += (nvc.PyNvVCException,)
        unsupported = getattr(nvc, "PyNvVCExceptionUnsupported", ())

        def native_call(method, *args, **kwargs):
            try:
                return method(*args, **kwargs)
            except native_errors as error:
                if isinstance(error, unsupported):
                    raise
                message = str(error)
            # 복구 예외가 이전 디코더와 패킷의 수명을 연장하지 않게 한다.
            method, args, kwargs = None, (), None
            raise _DecodeError(message)

        def reset(*, discard=True):
            nonlocal decoder, decode_stream, pixel_format, cleanup_failed
            if cleanup_failed or (
                slot.buffers is not None and slot.buffers._cleanup_failed
            ):
                return
            try:
                if decode_stream is not None:
                    decode_stream.synchronize()
                if discard:
                    slot.discard()
                if slot.buffers is not None:
                    slot.buffers.close()
                    if discard:
                        slot.buffers = None
            except BaseException:
                cleanup_failed = True
                if slot.buffers is not None:
                    slot.buffers._cleanup_failed = True
                raise
            # 외부 프레임 owner가 기존 풀과 디코더의 수명을 보장한다.
            decoder = decode_stream = pixel_format = None

        def resumed():
            nonlocal recovering
            if recovering:
                logger.info("디코더 복구 후 영상 출력을 재개했습니다.")
                recovering = False

        def stopped():
            return cancel.is_set() or (stop is not None and stop.is_set())

        def publish(frames):
            if not frames or stopped():
                return
            for frame in frames:
                if callable(getattr(frame, "__dlpack__", None)):
                    raise RuntimeError(
                        "GPU 디코딩에는 GetLockedFrame 잠금 API가 필요합니다."
                    )
                slot.publish(
                    PipelineContext(
                        frame=frame,
                        video_stream=video_stream,
                        cuda_stream=consumer_stream,
                        pixel_format=pixel_format,
                        decoded_at=time.perf_counter(),
                    )
                )
                resumed()

        def decode(packet_data):
            nonlocal pixel_format
            if not locked_decoder:
                publish(native_call(decoder.Decode, packet_data))
                return
            count = native_call(decoder.GetNumDecodedFrame, packet_data)
            if not count:
                return
            if slot.buffers is None:
                pixel_format = native_call(decoder.GetPixelFormat)
                slot.buffers = _DecoderBuffers(
                    decoder, decode_stream, pixel_format, native_call
                )
            buffers = slot.buffers
            for _ in range(count):
                slot.make_room()
                if not buffers.available(stopped):
                    return
                frame, owner = buffers.acquire(native_call)
                slot.publish(
                    PipelineContext(
                        frame=frame,
                        _decode_buffer=owner,
                        video_stream=video_stream,
                        cuda_stream=consumer_stream,
                        pixel_format=pixel_format,
                        decoded_at=time.perf_counter(),
                    )
                )
                resumed()
                del frame, owner
            buffers.reap()

        try:
            for item in inputs:
                if stopped():
                    return
                if video_stream is not None and item.video_stream is not video_stream:
                    logger.warning("입력 스트림이 변경되어 디코더를 초기화하고 키프레임을 기다립니다.")
                    reset()
                    waiting_keyframe = recovering = True
                video_stream = item.video_stream
                packet = item.packet
                try:
                    if waiting_keyframe and not getattr(packet, "is_keyframe", False):
                        continue
                    try:
                        if decoder is None:
                            codec_ids = {
                                "h264": nvc.cudaVideoCodec.H264,
                                "hevc": nvc.cudaVideoCodec.HEVC,
                                "h265": nvc.cudaVideoCodec.HEVC,
                            }
                            codec = codec_ids[video_stream.codec.name.lower()]
                            decode_stream = torch.cuda.Stream(device=self.gpu_id)
                            if consumer_stream is None:
                                consumer_stream = torch.cuda.Stream(device=self.gpu_id)
                            decoder = native_call(
                                nvc.CreateDecoder,
                                gpuid=self.gpu_id,
                                codec=codec,
                                usedevicememory=True,
                                outputColorType=nvc.OutputColorType.NATIVE,
                                latency=nvc.DisplayDecodeLatencyType.NATIVE,
                                cudastream=decode_stream.cuda_stream,
                            )
                            pixel_format = native_call(decoder.GetPixelFormat)
                            locked_decoder = all(
                                callable(getattr(decoder, name, None))
                                for name in ("GetNumDecodedFrame", "GetLockedFrame", "UnlockFrame")
                            )
                        packet_data = nvc.PacketData()
                        # 디코더가 비트스트림을 소비할 때까지 패킷 소유자를 유지한다.
                        packet_data.bsl_data = packet.buffer_ptr
                        packet_data.bsl = packet.size
                        if packet.pts is not None:
                            packet_data.pts = int(packet.pts)
                        with torch.cuda.stream(decode_stream):
                            decode(packet_data)
                        waiting_keyframe = False
                    except _DecodeError as error:
                        logger.warning(
                            "디코더 오류로 자동 복구를 시도합니다. 다음 키프레임을 기다립니다: %s",
                            error,
                        )
                        reset()
                        waiting_keyframe = recovering = True
                finally:
                    del item, packet

            if decoder is not None and not stopped():
                try:
                    with torch.cuda.stream(decode_stream):
                        if locked_decoder:
                            decode(nvc.PacketData())
                        else:
                            publish(native_call(decoder.Flush))
                except _DecodeError as error:
                    logger.warning("디코더 종료 처리 오류로 지연 프레임을 버립니다: %s", error)
        finally:
            reset(discard=False)

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

        worker = Thread(
            target=lambda: context.run(produce),
            name="pipeworks-nvidia-decode",
            daemon=True,
        )
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
