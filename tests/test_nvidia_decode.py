from contextlib import nullcontext
from contextvars import ContextVar
import ctypes
from fractions import Fraction
import gc
import os
from pathlib import Path
import sys
import time
from threading import Event, Thread, get_ident
from types import SimpleNamespace
import unittest
import weakref
from unittest.mock import patch

import torch

from pipeworks.embedded.nvidia_decode import NvidiaDecode
from pipeworks.models import PipelineContext


class Packet:
    def __init__(self, value, pts=None):
        self.value, self.pts = value, pts
        self._buffer = ctypes.create_string_buffer(bytes([value]))
        self.buffer_ptr = ctypes.addressof(self._buffer)
        self.size = 1

    def __bytes__(self):
        raise AssertionError("packet bytes must not be copied")


def context(value=1, codec="h264", pts=None):
    return PipelineContext(packet=Packet(value, pts), video_stream=SimpleNamespace(codec=SimpleNamespace(name=codec)))


class DecodeTests(unittest.TestCase):
    def setup_decoder(self, decode, flush=lambda: []):
        decoder = SimpleNamespace(GetPixelFormat=lambda: "NV12", Decode=decode, Flush=flush)
        api = SimpleNamespace(cudaVideoCodec=SimpleNamespace(H264=1, HEVC=2),
                              OutputColorType=SimpleNamespace(NATIVE=1),
                              DisplayDecodeLatencyType=SimpleNamespace(NATIVE=1),
                              PacketData=lambda: SimpleNamespace(), CreateDecoder=lambda **kwargs: decoder)
        module_patch = patch.dict(sys.modules, {"PyNvVideoCodec": api})
        module_patch.start()
        self.addCleanup(module_patch.stop)
        stream_patch = patch("pipeworks.embedded.nvidia_decode.torch.cuda.Stream", side_effect=lambda **kwargs: SimpleNamespace(cuda_stream=0))
        stream_patch.start()
        self.addCleanup(stream_patch.stop)
        scope_patch = patch("pipeworks.embedded.nvidia_decode.torch.cuda.stream", return_value=nullcontext())
        scope_patch.start()
        self.addCleanup(scope_patch.stop)
        step = NvidiaDecode()
        step.configure(SimpleNamespace(gpu_id=0))
        return step, api

    def test_producer_continues_and_preserves_fifo(self):
        continue_input, produced = Event(), Event()
        first_thread = get_ident()
        threads = []
        def decode(packet):
            threads.append(get_ident())
            return [packet.pts]
        step, _ = self.setup_decoder(decode)
        def inputs():
            yield context(1, pts=1)
            continue_input.wait(2)
            yield context(2, pts=2)
            yield context(3, pts=3)
            produced.set()
        output = step.process(inputs())
        self.addCleanup(output.close)
        self.assertEqual(next(output).frame, 1)
        continue_input.set()
        self.assertTrue(produced.wait(2))
        latest = next(output)
        self.assertEqual(latest.frame, 2)
        self.assertEqual(latest.decode_dropped_frames, 0)
        self.assertGreaterEqual(latest.processing_started_at, latest.decoded_at)
        self.assertTrue(all(thread != first_thread for thread in threads))
        self.assertEqual([item.frame for item in output], [3])

    def test_packet_codec_and_flush_contract(self):
        seen, create = [], []
        def decode(packet):
            self.assertEqual(packet.bsl_data, item.packet.buffer_ptr)
            self.assertEqual(packet.bsl, item.packet.size)
            seen.append((ctypes.string_at(packet.bsl_data, packet.bsl), getattr(packet, "pts", None)))
            return []
        delayed = object()
        step, api = self.setup_decoder(decode, lambda: [delayed])
        original = api.CreateDecoder
        api.CreateDecoder = lambda **kwargs: (create.append(kwargs), original(**kwargs))[1]
        item = context(7, codec="hevc", pts=123)
        results = list(step.process(iter([item])))
        self.assertEqual(seen, [(b"\x07", 123)])
        self.assertEqual(create[0]["codec"], 2)
        self.assertEqual(create[0]["gpuid"], 0)
        self.assertIs(results[0].frame, delayed)
        self.assertIs(results[0].video_stream, item.video_stream)
        self.assertEqual(results[0].pixel_format, "NV12")
        self.assertIsNot(results[0], item)

    def test_many_frames_and_flush_preserve_fifo(self):
        step, _ = self.setup_decoder(lambda packet: [1, 2, 3], lambda: [4, 5])
        produced = Event()
        from pipeworks.embedded.nvidia_decode import _FrameQueue
        original_take, original_finish = _FrameQueue.take, _FrameQueue.finish
        def take(slot, stop=None):
            self.assertTrue(produced.wait(2))
            return original_take(slot, stop)
        def finish(slot, error=None):
            original_finish(slot, error)
            produced.set()
        with patch.object(_FrameQueue, "take", take), patch.object(_FrameQueue, "finish", finish):
            results = list(step.process(iter([context()])))
        self.assertEqual([item.frame for item in results], [1, 2, 3, 4, 5])
        self.assertEqual(results[0].decode_dropped_frames, 0)

    def test_slot_is_bounded_and_errors_take_priority(self):
        from pipeworks.embedded.nvidia_decode import _FrameQueue
        slot = _FrameQueue()
        for value in range(100):
            slot.publish(PipelineContext(frame=value))
        slot.finish()
        self.assertEqual(len(slot.pending), 30)
        self.assertEqual(slot.dropped, 70)
        self.assertEqual([slot.take().frame for _ in range(30)], list(range(70, 100)))
        self.assertIsNone(slot.take())
        slot = _FrameQueue()
        slot.publish(PipelineContext(frame=1))
        slot.finish(ValueError("failed"))
        with self.assertRaisesRegex(ValueError, "failed"):
            slot.take()

    def test_queue_cancel_releases_all_pending_frames(self):
        from pipeworks.embedded.nvidia_decode import _FrameQueue
        slot = _FrameQueue()
        refs = []
        for value in range(30):
            item = PipelineContext(frame=value)
            refs.append(weakref.ref(item))
            slot.publish(item)
        del item
        slot.cancel()
        self.assertEqual(len(slot.pending), 0)
        self.assertTrue(all(ref() is None for ref in refs))
        slot.publish(PipelineContext(frame=31))
        self.assertIsNone(slot.take())

    def test_empty_input_and_producer_error(self):
        step, _ = self.setup_decoder(lambda packet: [])
        self.assertEqual(list(step.process(iter(()))), [])
        def failed():
            raise ValueError("source failed")
            yield
        with self.assertRaisesRegex(ValueError, "source failed"):
            list(step.process(failed()))

    def test_decode_error_wakes_consumer(self):
        def failed(packet):
            raise RuntimeError("decode failed")
        step, _ = self.setup_decoder(failed)
        with self.assertRaisesRegex(RuntimeError, "decode failed"):
            list(step.process(iter([context()])))

    def test_decode_error_closes_upstream_in_producer(self):
        owner_thread, closed = get_ident(), []
        def failed(packet):
            raise RuntimeError("decode failed")
        step, _ = self.setup_decoder(failed)
        def inputs():
            try:
                yield context()
            finally:
                closed.append(get_ident())
        with self.assertRaisesRegex(RuntimeError, "decode failed"):
            list(step.process(inputs()))
        self.assertEqual(len(closed), 1)
        self.assertNotEqual(closed[0], owner_thread)

    def test_worker_inherits_context_and_closes_input_on_cancel(self):
        from pipeworks.execution import current_source_cancel
        marker = ContextVar("decode_test_marker", default=None)
        observed, closed, reading = [], Event(), Event()
        step, _ = self.setup_decoder(lambda packet: (observed.append(marker.get()), [1])[1])
        def inputs():
            try:
                yield context()
                reading.set()
                self.assertTrue(current_source_cancel().wait(2))
            finally:
                closed.set()
        token = marker.set("pipeline")
        try:
            output = step.process(inputs())
            next(output)
            self.assertTrue(reading.wait(2))
            output.close()
        finally:
            marker.reset(token)
        self.assertTrue(closed.is_set())
        self.assertEqual(observed, ["pipeline"])

    def test_nonrecovering_hotswap_does_not_accumulate_inputs(self):
        from pipeworks.hotswap import Hotswap, _Cursor, _InputEpoch
        owner = Hotswap(NvidiaDecode(), recover_errors=False, watch_code=False)
        segment = _InputEpoch(_Cursor(iter(context(i % 255) for i in range(1000))), owner, ())
        list(segment)
        self.assertEqual(segment.unacknowledged, [])

    def test_hotswap_close_cancels_decoder_and_upstream(self):
        from pipeworks.execution import current_source_cancel
        from pipeworks.hotswap import Hotswap
        reading, closed = Event(), Event()
        step, _ = self.setup_decoder(lambda packet: [1])
        wrapped = Hotswap(step, recover_errors=False, watch_code=False)
        wrapped.configure(SimpleNamespace())
        def inputs():
            try:
                yield context()
                reading.set()
                current_source_cancel().wait(2)
            finally:
                closed.set()
        output = wrapped.process(inputs())
        try:
            self.assertEqual(next(output).frame, 1)
            self.assertTrue(reading.wait(2))
        finally:
            output.close()
        self.assertTrue(closed.is_set())

    def test_pipeline_stop_wakes_idle_consumer_and_cancels_upstream(self):
        from pipeworks.execution import current_source_cancel
        reading, closed, stop = Event(), Event(), Event()
        step, _ = self.setup_decoder(lambda packet: [])
        step._pipeworks_stop_event = stop
        def inputs():
            try:
                reading.set()
                current_source_cancel().wait(2)
                if False:
                    yield context()
            finally:
                closed.set()
        results = []
        runner = Thread(target=lambda: results.extend(step.process(inputs())))
        runner.start()
        try:
            self.assertTrue(reading.wait(2))
            stop.set()
            runner.join(2)
            self.assertFalse(runner.is_alive())
            self.assertTrue(closed.is_set())
            self.assertEqual(results, [])
        finally:
            stop.set()
            runner.join(2)

    def test_rtsp_retry_is_interrupted_by_decode_cancellation(self):
        import av
        from pipeworks.execution import _source_cancel_scope
        from pipeworks.embedded import RTSPSource
        cancel = Event()
        source = RTSPSource("rtsp://test")
        source.configure(SimpleNamespace(reconnect_interval_ms=60000))
        def failed(*args, **kwargs):
            cancel.set()
            raise av.error.FFmpegError(1, "failed")
        with _source_cancel_scope(cancel), patch("pipeworks.embedded.rtsp_source.av.open", side_effect=failed) as open_source:
            self.assertEqual(list(source.process(iter(()))), [])
        self.assertEqual(open_source.call_count, 1)


@unittest.skipUnless(torch.cuda.is_available(), "CUDA가 필요합니다.")
class DecodeCudaTests(unittest.TestCase):
    def test_reused_decoder_buffer_cannot_change_consumed_frame(self):
        first_consumed, updated = Event(), Event()
        backings = [torch.zeros((6, 8), dtype=torch.uint8, device="cuda") for _ in range(4)]
        torch.cuda.synchronize()
        locked, pending = set(), []
        def decode(packet):
            if not getattr(packet, "bsl", 0):
                return 0
            backing = next(t for t in backings if t.data_ptr() not in locked)
            backing.fill_(packet.pts)
            pending.append(backing.data_ptr())
            return 1
        def acquire():
            pointer = pending.pop(0)
            locked.add(pointer)
            return pointer
        decoder = SimpleNamespace(GetPixelFormat=lambda: "NV12", GetNumDecodedFrame=decode,
                                  GetLockedFrame=acquire, UnlockFrame=locked.remove,
                                  GetWidth=lambda: 8, GetHeight=lambda: 4, GetFrameSize=lambda: 48)
        api = SimpleNamespace(cudaVideoCodec=SimpleNamespace(H264=1, HEVC=2),
                              OutputColorType=SimpleNamespace(NATIVE=1),
                              DisplayDecodeLatencyType=SimpleNamespace(NATIVE=1),
                              PacketData=lambda: SimpleNamespace(bsl=0), CreateDecoder=lambda **kwargs: decoder)
        def inputs():
            yield context(1, pts=1)
            first_consumed.wait(2)
            yield context(2, pts=2)
            updated.set()
        step = NvidiaDecode()
        step.configure(SimpleNamespace())
        with patch.dict(sys.modules, {"PyNvVideoCodec": api}):
            output = step.process(inputs())
            try:
                first = next(output)
                first_consumed.set()
                self.assertTrue(updated.wait(2))
                second = next(output)
                self.assertTrue(torch.all(first.frame == 1).item())
                self.assertTrue(torch.all(second.frame == 2).item())
                self.assertIn(first.frame.data_ptr(), {t.data_ptr() for t in backings})
                self.assertEqual(first.frame.data_ptr(), first._decode_buffer.pointer)
                self.assertIs(first.cuda_stream, second.cuda_stream)
                self.assertEqual(list(output), [])
            finally:
                first_consumed.set()
                output.close()
            self.assertEqual(len(locked), 2)
            del first, second
            gc.collect()
            self.assertEqual(locked, set())

    def test_shared_tensor_and_dlpack_alias_keep_buffer_owner(self):
        from pipeworks.embedded.nvidia_decode import _DecoderBuffers
        backing = torch.ones((6, 8), device="cuda", dtype=torch.uint8)
        stream = torch.cuda.Stream()
        unlocked = []
        decoder = SimpleNamespace(GetWidth=lambda: 8, GetHeight=lambda: 4, GetFrameSize=lambda: 48,
                                  GetLockedFrame=backing.data_ptr, UnlockFrame=unlocked.append)
        pool = _DecoderBuffers(decoder, stream, "NV12")
        frame, owner = pool.acquire()
        reference = weakref.ref(owner)
        alias = torch.from_dlpack(frame)
        self.assertEqual(alias.data_ptr(), backing.data_ptr())
        del frame, owner
        gc.collect()
        pool.reap()
        self.assertIsNotNone(reference())
        self.assertEqual(unlocked, [])
        del alias
        gc.collect()
        pool.close()
        self.assertIsNone(reference())
        self.assertEqual(unlocked, [backing.data_ptr()])


class BufferLifetimeTests(unittest.TestCase):
    def pool(self):
        from pipeworks.embedded.nvidia_decode import _DecoderBuffers
        unlocked = []
        decoder = SimpleNamespace(GetWidth=lambda: 8, GetHeight=lambda: 4, GetFrameSize=lambda: 48,
                                  UnlockFrame=unlocked.append)
        return _DecoderBuffers(decoder, SimpleNamespace(), "NV12"), unlocked

    def test_incomplete_event_prevents_unlock_until_completed(self):
        pool, unlocked = self.pool()
        event = SimpleNamespace(query=lambda: False, synchronize=lambda: None)
        pool.locked.add(123)
        pool.retire(123, event)
        pool.reap()
        self.assertEqual(unlocked, [])
        self.assertEqual(pool.locked, {123})
        event.query = lambda: True
        pool.reap()
        self.assertEqual(unlocked, [123])
        self.assertEqual(pool.locked, set())
        pool.close()

    def test_lock_limit_waits_for_buffer_return_and_is_cancellable(self):
        pool, _ = self.pool()
        pool.locked.update(range(pool.limit))
        stop, entered, done = Event(), Event(), Event()
        result = []
        def stopped():
            entered.set()
            return stop.is_set()
        runner = Thread(target=lambda: (result.append(pool.available(stopped)), done.set()))
        runner.start()
        try:
            self.assertTrue(entered.wait(2))
            self.assertFalse(done.is_set())
            stop.set()
            runner.join(2)
            self.assertEqual(result, [False])
        finally:
            stop.set()
            runner.join(2)
        pool.close()

    def test_close_drains_gpu_event_before_unlock(self):
        pool, _ = self.pool()
        calls = []
        event = SimpleNamespace(query=lambda: False, synchronize=lambda: calls.append("wait"))
        pool.decoder.UnlockFrame = lambda pointer: calls.append("unlock")
        pool.locked.add(123)
        pool.retire(123, event)
        pool.close()
        self.assertEqual(calls, ["wait", "unlock"])
        self.assertEqual(pool.locked, set())


@unittest.skipUnless(torch.cuda.is_available(), "CUDA가 필요합니다.")
class NativeDecodeTests(unittest.TestCase):
    def setUp(self):
        self.dll_handles = []
        if os.name == "nt":
            package = Path(sys.prefix) / "Lib/site-packages/PyNvVideoCodec"
            for directory in (package, Path(torch.__file__).parent / "lib"):
                if directory.exists():
                    self.dll_handles.append(os.add_dll_directory(str(directory)))
        try:
            import PyNvVideoCodec as nvc
        except ImportError as error:
            for handle in self.dll_handles:
                handle.close()
            self.skipTest(f"PyNvVideoCodec를 불러올 수 없습니다: {error}")
        self.nvc = nvc
        for handle in self.dll_handles:
            self.addCleanup(handle.close)

    def packets(self, count=24):
        import av
        codec = av.CodecContext.create("libx264", "w")
        codec.width = codec.height = 256
        codec.pix_fmt = "yuv420p"
        codec.time_base = Fraction(1, 30)
        codec.options = {"preset": "ultrafast", "tune": "zerolatency", "bf": "0"}
        packets = []
        for index in range(count):
            frame = av.VideoFrame(256, 256, "yuv420p")
            frame.pts = index
            for plane_index, plane in enumerate(frame.planes):
                plane.update(bytes([20 + index if plane_index == 0 else 128]) * plane.buffer_size)
            packets.extend(codec.encode(frame))
        packets.extend(codec.encode(None))
        return packets

    def test_native_locked_frame_survives_decode_and_encodes_without_copy(self):
        packets = self.packets(80)
        video_stream = SimpleNamespace(codec=SimpleNamespace(name="h264"))
        first_taken, progressed = Event(), Event()
        from pipeworks.embedded.nvidia_decode import _FrameQueue
        original_publish = _FrameQueue.publish
        published = []
        def publish(slot, item):
            original_publish(slot, item)
            self.assertLessEqual(len(slot.pending), 30)
            published.append(item._decode_buffer.pointer)
            if len(published) == 1:
                self.assertTrue(first_taken.wait(5))
            if len(published) >= 70:
                self.assertGreater(slot.dropped, 0)
                progressed.set()
        step = NvidiaDecode()
        step.configure(SimpleNamespace())
        inputs = (PipelineContext(packet=packet, video_stream=video_stream) for packet in packets)
        with patch.object(_FrameQueue, "publish", publish), \
             patch.object(torch.Tensor, "clone", side_effect=AssertionError("영상 복사 금지")), \
             patch.object(torch.cuda.Stream, "synchronize", side_effect=AssertionError("프레임별 CPU 스트림 동기화 금지")):
            output = step.process(inputs)
            try:
                first = next(output)
                baseline = first.frame.cpu()
                pointer = first.frame.data_ptr()
                pool = first._decode_buffer.pool
                self.assertEqual(pointer, first._decode_buffer.pointer)
                first_taken.set()
                self.assertTrue(progressed.wait(5))
                self.assertTrue(torch.equal(first.frame.cpu(), baseline))
                self.assertLessEqual(len(pool.locked), pool.limit)
                encoder = self.nvc.CreateEncoder(256, 256, "NV12", False, gpu_id=0,
                                                 codec="h264", bf=0, fps=30,
                                                 cudastream=first.cuda_stream.cuda_stream)
                with torch.cuda.stream(first.cuda_stream):
                    encoder.Encode(first.frame)
                del first
                consumed = 1
                for item in output:
                    self.assertEqual(item.frame.data_ptr(), item._decode_buffer.pointer)
                    with torch.cuda.stream(item.cuda_stream):
                        encoder.Encode(item.frame)
                    consumed += 1
                    del item
                self.assertGreaterEqual(consumed, 2)
                with torch.cuda.stream(pool.stream):
                    encoder.EndEncode()
                gc.collect()
                self.assertEqual(pool.locked, set())
            finally:
                first_taken.set()
                output.close()

    def test_native_early_close_keeps_external_dlpack_alias_locked(self):
        packets = self.packets()
        stream = SimpleNamespace(codec=SimpleNamespace(name="h264"))
        step = NvidiaDecode()
        step.configure(SimpleNamespace())
        output = step.process(PipelineContext(packet=p, video_stream=stream) for p in packets)
        try:
            first = next(output)
            pool = first._decode_buffer.pool
            alias = torch.from_dlpack(first.frame)
            pointer = alias.data_ptr()
            del first
        finally:
            output.close()
        gc.collect()
        self.assertEqual(pool.locked, {pointer})
        del alias
        gc.collect()
        self.assertEqual(pool.locked, set())

    def test_native_decode_multistage_async_does_not_exhaust_locks(self):
        from pipeworks.embedded import CudaAsync, Tap
        from pipeworks.hotswap import Hotswap
        from pipeworks.models import Step

        class Stage(Step):
            def __init__(self, delay):
                self.delay = delay
            def process(self, inputs):
                for item in inputs:
                    time.sleep(self.delay)
                    yield item

        packets = self.packets(200)
        stream = SimpleNamespace(codec=SimpleNamespace(name="h264"))
        stop = Event()
        step = NvidiaDecode()
        step.configure(SimpleNamespace())
        step._pipeworks_stop_event = stop
        wrapper = CudaAsync(*(Hotswap(Stage(delay), recover_errors=False, watch_code=False)
                              for delay in (.0002, .0005, .0002)), timeout_ms=1)
        tap = Tap(Hotswap(Stage(.025), recover_errors=False, watch_code=False))
        state = {"inputs": 0, "outputs": 0, "error": None}
        def inputs():
            for packet in packets:
                time.sleep(.002)
                state["inputs"] += 1
                yield PipelineContext(packet=packet, video_stream=stream)
        def consume():
            try:
                for item in tap.process(wrapper.process(step.process(inputs()))):
                    state["outputs"] += 1
                    state["pool"] = item._decode_buffer.pool
                    time.sleep(.001)
            except BaseException as error:
                state["error"] = error
        runner = Thread(target=consume)
        runner.start()
        try:
            runner.join(5)
            self.assertFalse(runner.is_alive(),
                             f"디코더 정체: 입력 {state['inputs']}, 출력 {state['outputs']}")
            self.assertIsNone(state["error"])
            self.assertEqual(state["inputs"], len(packets))
            self.assertGreater(state["outputs"], 4)
        finally:
            stop.set()
            runner.join(3)

    def test_native_decode_hotswap_tap_and_overlay_keep_progressing(self):
        import importlib.util
        from pipeworks.embedded import Tap, NvidiaEncode
        from pipeworks.hotswap import Hotswap
        from pipeworks.models import Step

        path = Path(__file__).resolve().parents[1] / "examples/step/box_overlay.py"
        spec = importlib.util.spec_from_file_location("decode_test_overlay", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        class Stage(Step):
            def __init__(self, delay=0):
                self.delay = delay
            def process(self, inputs):
                first = True
                for item in inputs:
                    time.sleep(self.delay)
                    if not self.delay:
                        item.detections = (SimpleNamespace(boxes=SimpleNamespace(
                            xyxy=torch.tensor([[10., 10., 40., 40.]], device=item.cuda_stream.device))) if first else None)
                        first = False
                    yield item

        packets = self.packets(200)
        video = SimpleNamespace(codec=SimpleNamespace(name="h264"),
                                codec_context=SimpleNamespace(name="h264", width=256, height=256))
        stop = Event()
        decode = NvidiaDecode()
        decode.configure(SimpleNamespace())
        decode._pipeworks_stop_event = stop
        def wrapped(step):
            step.configure(SimpleNamespace(keep_previous=False))
            return Hotswap(step, recover_errors=False, watch_code=False)
        state = {"inputs": 0, "outputs": 0, "error": None}
        def inputs():
            for packet in packets:
                time.sleep(.01)
                state["inputs"] += 1
                yield PipelineContext(packet=packet, video_stream=video)
        def consume():
            output = decode.process(inputs())
            for step in [wrapped(Stage()), wrapped(module.BoxOverlay()),
                         Tap(wrapped(Stage(.1))), wrapped(NvidiaEncode())]:
                output = step.process(output)
            try:
                for item in output:
                    state["outputs"] += 1
            except BaseException as error:
                state["error"] = error
            finally:
                output.close()
        runner = Thread(target=consume)
        runner.start()
        try:
            runner.join(5)
            self.assertFalse(runner.is_alive(), f"예제 조합 정체: {state}")
            self.assertIsNone(state["error"])
            self.assertEqual(state["inputs"], len(packets))
            self.assertGreater(state["outputs"], 20)
        finally:
            stop.set()
            runner.join(3)
