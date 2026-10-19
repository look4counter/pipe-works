from contextlib import nullcontext
from fractions import Fraction
from io import BytesIO
import gc
import os
from pathlib import Path
import sys
from threading import Event
from types import SimpleNamespace
import unittest
import weakref
from unittest.mock import Mock, patch

import av
import torch

from pipeworks.embedded.nvidia_encode import NvidiaEncode
from pipeworks.models import PipelineContext


class Encoder:
    def Encode(self, frame):
        return bytes([frame])

    def EndEncode(self):
        return []


class EncodeTests(unittest.TestCase):
    def setUp(self):
        self.clock = 0.0
        self.created = []
        self.video = SimpleNamespace(
            codec_context=SimpleNamespace(name="h264", width=256, height=256)
        )
        self.stream = SimpleNamespace(cuda_stream=17, synchronize=Mock())
        self.api = SimpleNamespace(CreateEncoder=self.create)
        for patcher in (
            patch.dict(sys.modules, {"PyNvVideoCodec": self.api}),
            patch("pipeworks.embedded.nvidia_encode.torch.cuda.stream", return_value=nullcontext()),
            patch("pipeworks.embedded.nvidia_encode.time.monotonic", side_effect=lambda: self.clock),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.step = NvidiaEncode()
        self.step.configure(SimpleNamespace())

    def create(self, *args, **kwargs):
        self.created.append((args, kwargs))
        return Encoder()

    def item(self, value=1, **kwargs):
        return PipelineContext(
            frame=value,
            video_stream=kwargs.get("video_stream", self.video),
            cuda_stream=kwargs.get("cuda_stream", self.stream),
            pixel_format=kwargs.get("pixel_format", "NV12"),
        )

    def test_normal_packet_contract_and_flush(self):
        encoder = Encoder()
        encoder.Encode = lambda frame: [b"a", b"b"]
        encoder.EndEncode = lambda: b"c"
        self.api.CreateEncoder = lambda *args, **kwargs: encoder
        result = list(self.step.process(iter([self.item()])))
        self.assertEqual([bytes(item.packet) for item in result], [b"a", b"b", b"c"])
        self.assertEqual([item.packet.pts for item in result], [0, 1, 2])
        self.assertEqual([item.packet.dts for item in result], [0, 1, 2])
        self.assertTrue(all(item.packet.time_base == Fraction(1, 30) for item in result))
        self.assertTrue(all(item.packet.duration == 1 for item in result))
        self.assertTrue(all(item.video_stream is result[0].video_stream for item in result))
        self.assertIsNot(result[0].video_stream, self.video)
        self.assertEqual(result[0].video_stream.time_base, Fraction(1, 30))
        self.assertTrue(all(not hasattr(item, "frame") for item in result))

    def test_encode_failure_recreates_after_one_second_and_preserves_timestamps(self):
        first = Encoder()
        first.EndEncode = Mock(side_effect=AssertionError("실패 인코더 종료 호출 금지"))

        def encode(frame):
            if frame == 2:
                raise RuntimeError("Encode occured error")
            return bytes([frame])

        first.Encode = encode
        original = self.api.CreateEncoder

        def create(*args, **kwargs):
            result = original(*args, **kwargs)
            return first if len(self.created) == 1 else result

        self.api.CreateEncoder = create

        def inputs():
            yield self.item(1)
            yield self.item(2)
            self.clock = 0.999
            yield self.item(3)
            self.clock = 1.0
            yield self.item(4)

        with self.assertLogs("pipeworks.embedded.nvidia_encode", level="INFO") as logs:
            result = list(self.step.process(inputs()))
        self.assertEqual([bytes(item.packet) for item in result], [b"\x01", b"\x04"])
        self.assertEqual([item.packet.dts for item in result], [0, 1])
        self.assertEqual(len(self.created), 2)
        self.assertTrue(all(kwargs["repeatspspps"] == 1 for _, kwargs in self.created))
        self.assertEqual(self.stream.synchronize.call_count, 2)
        first.EndEncode.assert_not_called()
        self.assertTrue(any("Encode occured error" in line for line in logs.output))
        self.assertTrue(any("재개" in line for line in logs.output))

    def test_native_creation_failure_retries_without_accumulating_frames(self):
        class NativeError(Exception):
            pass

        self.api.PyNvVCException = NativeError
        attempts, consumed = [], []

        def create(*args, **kwargs):
            attempts.append(self.clock)
            if len(attempts) < 3:
                raise NativeError("native create failed")
            return Encoder()

        self.api.CreateEncoder = create

        def inputs():
            for at, value in [(0, 1), (0.5, 2), (1, 3), (1.5, 4), (2, 5)]:
                self.clock = at
                consumed.append(value)
                yield self.item(value)

        result = list(self.step.process(inputs()))
        self.assertEqual(attempts, [0, 1, 2])
        self.assertEqual(consumed, [1, 2, 3, 4, 5])
        self.assertEqual([bytes(item.packet) for item in result], [b"\x05"])
        self.assertEqual(self.stream.synchronize.call_count, 3)

    def test_end_encode_failure_is_discarded(self):
        encoder = Encoder()
        encoder.EndEncode = Mock(side_effect=RuntimeError("flush failed"))
        self.api.CreateEncoder = lambda *args, **kwargs: encoder
        result = list(self.step.process(iter([self.item()])))
        self.assertEqual(len(result), 1)
        encoder.EndEncode.assert_called_once()

    def test_stream_and_format_changes_recreate_using_latest_metadata(self):
        new_video = SimpleNamespace(
            codec_context=SimpleNamespace(name="hevc", width=512, height=256)
        )
        new_cuda = SimpleNamespace(cuda_stream=23, synchronize=Mock())

        def inputs():
            yield self.item(1)
            yield self.item(2, video_stream=new_video)
            new_video.codec_context.width = 768
            yield self.item(3, video_stream=new_video)
            yield self.item(4, video_stream=new_video, pixel_format="P010")
            yield self.item(5, video_stream=new_video, pixel_format="P010", cuda_stream=new_cuda)

        result = list(self.step.process(inputs()))
        self.assertEqual(len(self.created), 5)
        self.assertEqual([args[:3] for args, _ in self.created], [
            (256, 256, "NV12"), (512, 256, "NV12"), (768, 256, "NV12"),
            (768, 256, "P010"), (768, 256, "P010"),
        ])
        self.assertEqual(self.created[-1][1]["cudastream"], 23)
        self.assertEqual(result[0].video_stream.width, 256)
        self.assertEqual([item.video_stream.width for item in result[1:]], [512, 768, 768, 768])
        self.assertEqual(len({item.video_stream.connection_id for item in result}), 5)
        self.assertEqual([item.packet.pts for item in result], list(range(5)))

    def test_same_format_new_stream_recreates_and_flushes_with_old_metadata(self):
        encoder = Encoder()
        encoder.EndEncode = lambda: b"tail"
        self.api.CreateEncoder = Mock(side_effect=[encoder, Encoder()])
        new_video = SimpleNamespace(codec_context=self.video.codec_context)
        result = list(self.step.process(iter([self.item(1), self.item(2, video_stream=new_video)])))
        self.assertEqual(self.api.CreateEncoder.call_count, 2)
        self.assertEqual([bytes(item.packet) for item in result], [b"\x01", b"tail", b"\x02"])
        self.assertIs(result[1].video_stream, result[0].video_stream)
        self.assertNotEqual(result[2].video_stream.connection_id, result[0].video_stream.connection_id)

    def test_output_metadata_uses_encoder_headers_once_per_generation(self):
        from pipeworks.video import encoded_stream_info

        self.video.codec_context.extradata = b"input header"
        encoder = Encoder()
        header = b"\x00\x00\x01\x67sps\x00\x00\x01\x68pps"
        encoder.Encode = lambda frame: header + b"\x00\x00\x01\x65frame"
        self.api.CreateEncoder = lambda *args, **kwargs: encoder
        with patch("pipeworks.embedded.nvidia_encode.encoded_stream_info",
                   wraps=encoded_stream_info) as snapshot:
            results = list(self.step.process(iter([self.item(), self.item()])))
        self.assertEqual(snapshot.call_count, 1)
        info = results[0].video_stream
        self.assertIs(info, results[1].video_stream)
        self.assertNotIn(b"input header", info.codec_context.extradata)
        self.assertIn(b"sps", info.codec_context.extradata)
        self.assertIn(b"pps", info.codec_context.extradata)

    def test_unsupported_and_non_native_errors_recover(self):
        class Unsupported(RuntimeError):
            pass

        self.api.PyNvVCExceptionUnsupported = Unsupported
        self.api.CreateEncoder = Mock(side_effect=Unsupported("unsupported"))
        self.assertEqual(list(self.step.process(iter([self.item()]))), [])
        self.api.CreateEncoder = lambda *args, **kwargs: Encoder()
        with patch("pipeworks.embedded.nvidia_encode.record_stage", side_effect=RuntimeError("report failed")):
            self.assertEqual(len(list(self.step.process(iter([self.item()])))), 1)
        encoder = Encoder()
        encoder.Encode = lambda frame: object()
        self.api.CreateEncoder = lambda *args, **kwargs: encoder
        self.assertEqual(list(self.step.process(iter([self.item()]))), [])

    def test_source_and_downstream_errors_propagate_and_release_encoder(self):
        refs = []

        def create(*args, **kwargs):
            encoder = Encoder()
            refs.append(weakref.ref(encoder))
            return encoder

        self.api.CreateEncoder = create

        def failed_input():
            yield self.item()
            raise RuntimeError("source failed")

        output = self.step.process(failed_input())
        next(output)
        with self.assertRaisesRegex(RuntimeError, "source failed"):
            next(output)
        gc.collect()
        self.assertIsNone(refs[-1]())
        output = self.step.process(iter([self.item()]))
        next(output)
        with self.assertRaisesRegex(RuntimeError, "downstream failed"):
            output.throw(RuntimeError("downstream failed"))
        gc.collect()
        self.assertIsNone(refs[-1]())

    def test_stop_during_recovery_does_not_retry_or_flush(self):
        stop = Event()
        self.step._pipeworks_stop_event = stop
        self.api.CreateEncoder = Mock(side_effect=RuntimeError("create failed"))

        def inputs():
            yield self.item()
            stop.set()
            self.clock = 2
            yield self.item()

        self.assertEqual(list(self.step.process(inputs())), [])
        self.assertEqual(self.api.CreateEncoder.call_count, 1)

    def test_cuda_scope_failure_and_gpu_sync_failure_propagate(self):
        with patch("pipeworks.embedded.nvidia_encode.torch.cuda.stream", side_effect=RuntimeError("cuda scope failed")):
            with self.assertRaisesRegex(RuntimeError, "cuda scope failed"):
                list(self.step.process(iter([self.item()])))
        encoder = Encoder()
        encoder.Encode = Mock(side_effect=RuntimeError("encode failed"))
        self.api.CreateEncoder = lambda *args, **kwargs: encoder
        self.stream.synchronize.side_effect = RuntimeError("GPU unavailable")
        with self.assertRaisesRegex(RuntimeError, "GPU unavailable"):
            list(self.step.process(iter([self.item()])))

    def test_recovery_completion_is_logged_only_when_packet_is_produced(self):
        encoder = Encoder()
        encoder.Encode = Mock(side_effect=[b"", b"ok"])
        self.api.CreateEncoder = Mock(side_effect=[RuntimeError("create failed"), encoder])
        output = None

        def inputs():
            yield self.item(1)
            self.clock = 1
            yield self.item(2)
            self.assertFalse(any("재개" in line for line in logs.output))
            yield self.item(3)

        with self.assertLogs("pipeworks.embedded.nvidia_encode", level="INFO") as logs:
            output = list(self.step.process(inputs()))
        self.assertEqual([bytes(item.packet) for item in output], [b"ok"])
        self.assertEqual(sum("재개" in line for line in logs.output), 1)

    def test_generator_close_releases_encoder_without_flushing(self):
        refs, flushed = [], []

        def create(*args, **kwargs):
            encoder = Encoder()
            encoder.EndEncode = lambda: flushed.append(True)
            refs.append(weakref.ref(encoder))
            return encoder

        self.api.CreateEncoder = create
        output = self.step.process(iter([self.item()]))
        next(output)
        output.close()
        gc.collect()
        self.assertIsNone(refs[0]())
        self.assertEqual(flushed, [])

    def test_empty_input_does_not_create_encoder(self):
        self.assertEqual(list(self.step.process(iter(()))), [])
        self.assertEqual(self.created, [])

    def test_recovery_releases_failed_encoder_while_its_stream_is_alive(self):
        events, refs = [], []

        class Stream:
            cuda_stream = 91

            def synchronize(self):
                events.append("sync")

            def __del__(self):
                events.append("stream")

        class FailingEncoder:
            def Encode(self, frame):
                raise RuntimeError("native failed")

            def __del__(self):
                events.append(("encoder", refs[0]() is not None))

        self.api.CreateEncoder = lambda *args, **kwargs: FailingEncoder()

        def inputs():
            stream = Stream()
            refs.append(weakref.ref(stream))
            yield self.item(cuda_stream=stream)
            del stream
            # 다음 입력으로 교체하면 직전 컨텍스트도 해제된다.
            yield self.item()

        with patch("pipeworks.embedded.nvidia_encode.torch.cuda.stream", new=lambda stream: nullcontext()):
            list(self.step.process(inputs()))
        self.assertEqual(events, ["sync", ("encoder", True), "stream"])

    def test_stream_replacement_and_close_wait_before_releasing_encoder(self):
        events = []

        class TrackedEncoder(Encoder):
            def __del__(self):
                events.append("encoder")

        self.api.CreateEncoder = lambda *args, **kwargs: TrackedEncoder()
        self.stream.synchronize.side_effect = lambda: events.append("sync")
        new_stream = SimpleNamespace(
            cuda_stream=23, synchronize=lambda: events.append("new-sync")
        )
        output = self.step.process(iter([
            self.item(), self.item(cuda_stream=new_stream)
        ]))
        next(output)
        next(output)
        output.close()
        self.assertEqual(events, ["sync", "encoder", "new-sync", "encoder"])

    def test_previous_frame_is_kept_until_replacement_finishes(self):
        refs, seen = [], []

        class Frame:
            pass

        class TrackedEncoder:
            def Encode(self, frame):
                return b"packet"

            def EndEncode(self):
                seen.append(refs[0]() is not None)
                return []

            def __del__(self):
                seen.append(refs[0]() is not None)

        self.api.CreateEncoder = lambda *args, **kwargs: TrackedEncoder()

        def inputs():
            frame = Frame()
            refs.append(weakref.ref(frame))
            yield self.item(frame)
            del frame
            yield self.item(video_stream=SimpleNamespace(codec_context=self.video.codec_context))

        list(self.step.process(inputs()))
        self.assertEqual(seen[:2], [True, True])
        self.assertIsNone(refs[0]())


@unittest.skipUnless(torch.cuda.is_available(), "CUDA가 필요합니다.")
class NativeEncodeRecoveryTests(unittest.TestCase):
    def setUp(self):
        handles = []
        if os.name == "nt":
            package = Path(sys.prefix) / "Lib/site-packages/PyNvVideoCodec"
            for directory in (package, Path(torch.__file__).parent / "lib"):
                if directory.exists():
                    handles.append(os.add_dll_directory(str(directory)))
        for handle in handles:
            self.addCleanup(handle.close)
        try:
            import PyNvVideoCodec as nvc
        except ImportError as error:
            self.skipTest(f"PyNvVideoCodec를 불러올 수 없습니다: {error}")
        self.nvc = nvc

    def test_recreated_encoder_produces_independently_decodable_stream(self):
        for codec in ("h264", "hevc"):
            with self.subTest(codec=codec):
                self.check_recovery(codec)

    def check_recovery(self, codec):
        original_create = self.nvc.CreateEncoder
        created, outputs, metadata = [], [], {}
        now = [0.0]
        stream = torch.cuda.Stream()
        video = SimpleNamespace(
            codec_context=SimpleNamespace(name=codec, width=256, height=256)
        )

        class FaultOnce:
            def __init__(self, encoder):
                self.encoder = encoder
                self.calls = 0

            def Encode(self, frame):
                self.calls += 1
                if self.calls == 10:
                    raise RuntimeError("주입된 인코딩 오류")
                return self.encoder.Encode(frame)

            def EndEncode(self):
                raise AssertionError("실패한 인코더의 지연 출력은 사용하지 않는다.")

        def create(*args, **kwargs):
            encoder = original_create(*args, **kwargs)
            created.append(kwargs)
            return FaultOnce(encoder) if len(created) == 1 else encoder

        def inputs():
            for index in range(40):
                now[0] = 0.0 if index < 10 else (0.5 if index < 15 else 1.0)
                with torch.cuda.stream(stream):
                    frame = torch.full((384, 256), 128, device="cuda", dtype=torch.uint8)
                    frame[:256].fill_(20 + index)
                yield PipelineContext(
                    frame=frame, video_stream=video, cuda_stream=stream, pixel_format="NV12"
                )

        step = NvidiaEncode()
        step.configure(SimpleNamespace())
        with (
            patch.object(self.nvc, "CreateEncoder", side_effect=create),
            patch("pipeworks.embedded.nvidia_encode.time.monotonic", side_effect=lambda: now[0]),
        ):
            for item in step.process(inputs()):
                outputs.append((len(created), item.packet))
                previous = metadata.setdefault(len(created), item.video_stream)
                self.assertIs(previous, item.video_stream)
        self.assertEqual(len(created), 2)
        self.assertTrue(all(config["repeatspspps"] == 1 for config in created))
        self.assertEqual([packet.pts for _, packet in outputs], list(range(len(outputs))))
        self.assertEqual([packet.dts for _, packet in outputs], list(range(len(outputs))))
        new_data = b"".join(bytes(packet) for generation, packet in outputs if generation == 2)
        self.assertGreater(len(new_data), 0)
        decoder = av.CodecContext.create(codec, "r")
        frames = []
        for packet in decoder.parse(new_data) + decoder.parse(b""):
            frames.extend(decoder.decode(packet))
        frames.extend(decoder.decode(None))
        self.assertEqual(len(frames), 25)
        self.assertTrue(frames[0].key_frame)
        self.assertEqual((frames[0].width, frames[0].height), (256, 256))
        self.assertNotEqual(metadata[1].connection_id, metadata[2].connection_id)
        self.assertTrue(metadata[2].codec_context.extradata)
        muxed = BytesIO()
        with av.open(muxed, "w", format="matroska") as output:
            output_stream = metadata[2].add_to_output(output)
            for generation, packet in outputs:
                if generation == 2:
                    packet.stream = output_stream
                    output.mux(packet)
        muxed.seek(0)
        with av.open(muxed) as source:
            frames = list(source.decode(video=0))
        self.assertEqual(len(frames), 25)
        self.assertEqual((frames[0].width, frames[0].height), (256, 256))


if __name__ == "__main__":
    unittest.main()
