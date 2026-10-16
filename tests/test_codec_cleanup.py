from types import SimpleNamespace
from threading import Event
import unittest
from unittest.mock import Mock, call, patch

from pipeworks.embedded.nvidia_decode import _DecoderBuffers


class BufferCleanupTests(unittest.TestCase):
    def pool(self):
        decoder = SimpleNamespace(
            GetWidth=lambda: 8, GetHeight=lambda: 4, GetFrameSize=lambda: 48,
            UnlockFrame=Mock(),
        )
        return _DecoderBuffers(decoder, SimpleNamespace(), "NV12")

    def event(self, ready=True):
        return SimpleNamespace(query=Mock(return_value=ready), synchronize=Mock())

    def test_success_is_removed_before_later_unlock_fails(self):
        pool = self.pool()
        first, second = self.event(), self.event()
        error = RuntimeError("second unlock failed")
        pool.decoder.UnlockFrame.side_effect = [None, error]
        pool.locked.update((1, 2))
        pool.retired = [(1, first), (2, second)]
        with self.assertRaises(RuntimeError) as caught:
            pool.reap()
        self.assertIs(caught.exception, error)
        self.assertEqual(pool.retired, [(2, second)])
        self.assertEqual(pool.locked, {2})

    def test_success_is_removed_before_later_event_fails(self):
        pool = self.pool()
        first, second = self.event(), self.event()
        second.synchronize.side_effect = RuntimeError("event failed")
        pool.locked.update((1, 2))
        pool.retired = [(1, first), (2, second)]
        with self.assertRaisesRegex(RuntimeError, "event failed"):
            pool.reap(wait=True)
        self.assertEqual(pool.retired, [(2, second)])
        self.assertEqual(pool.locked, {2})

    def test_unready_buffer_is_retained_when_later_query_fails(self):
        pool = self.pool()
        pending, ready, failed = self.event(False), self.event(), self.event()
        failed.query.side_effect = RuntimeError("query failed")
        pool.locked.update((1, 2, 3))
        pool.retired = [(1, pending), (2, ready), (3, failed)]
        with self.assertRaisesRegex(RuntimeError, "query failed"):
            pool.reap()
        self.assertEqual(pool.retired, [(1, pending), (3, failed)])
        self.assertEqual(pool.locked, {1, 3})

    def test_failed_unlock_is_not_retried_by_final_close_or_late_owner(self):
        pool = self.pool()
        event = self.event()
        pool.locked.update((1, 2, 3))
        pool.retired = [(1, event), (2, event)]
        error = RuntimeError("unlock failed")
        pool.decoder.UnlockFrame.side_effect = [None, error]
        with self.assertRaises(RuntimeError) as caught:
            pool.reap()
        self.assertIs(caught.exception, error)
        pool.close()
        pool.close()
        late_event = self.event()
        pool.retire(3, late_event)
        self.assertEqual(pool.decoder.UnlockFrame.call_args_list, [call(1), call(2)])
        late_event.synchronize.assert_not_called()
        self.assertEqual(pool.locked, {2, 3})
        with self.assertRaises(RuntimeError):
            pool.available(lambda: False)
        with self.assertRaises(RuntimeError):
            pool.acquire()

    def test_event_failure_is_not_retried_when_closing_pool(self):
        pool = self.pool()
        event = self.event()
        event.synchronize.side_effect = RuntimeError("sync failed")
        pool.locked.add(1)
        pool.retired = [(1, event)]
        with self.assertRaisesRegex(RuntimeError, "sync failed"):
            pool.close()
        pool.close()
        self.assertEqual(event.synchronize.call_count, 1)
        pool.decoder.UnlockFrame.assert_not_called()

    def test_closed_pool_late_owner_failure_is_not_retried(self):
        pool = self.pool()
        pool.close()
        pool.locked.add(1)
        pool.decoder.UnlockFrame.side_effect = RuntimeError("late unlock failed")
        with self.assertRaisesRegex(RuntimeError, "late unlock failed"):
            pool.retire(1, self.event())
        pool.close()
        self.assertEqual(pool.decoder.UnlockFrame.call_args_list, [call(1)])


class CodecCleanupTests(unittest.TestCase):
    def test_encoder_sync_failure_is_propagated_once(self):
        import test_nvidia_encode as fixtures

        case = fixtures.EncodeTests()
        case.setUp()
        self.addCleanup(case.doCleanups)
        encoder = fixtures.Encoder()
        encoder.Encode = Mock(side_effect=RuntimeError("encode failed"))
        case.api.CreateEncoder = lambda *args, **kwargs: encoder
        first = RuntimeError("first cleanup failed")
        case.stream.synchronize.side_effect = [first, RuntimeError("second cleanup failed")]
        with self.assertRaises(RuntimeError) as caught:
            list(case.step.process(iter([case.item()])))
        self.assertIs(caught.exception, first)
        self.assertEqual(case.stream.synchronize.call_count, 1)

    def test_decoder_sync_failure_is_propagated_once(self):
        import test_nvidia_decode as fixtures
        from pipeworks.embedded.nvidia_decode import _FrameQueue

        case = fixtures.DecodeTests()
        self.addCleanup(case.doCleanups)
        step, _ = case.setup_decoder(Mock(side_effect=RuntimeError("decode failed")))
        first = RuntimeError("first cleanup failed")
        stream = SimpleNamespace(cuda_stream=1, synchronize=Mock(
            side_effect=[first, RuntimeError("second cleanup failed")],
        ))
        with patch("pipeworks.embedded.nvidia_decode.torch.cuda.Stream", return_value=stream):
            with self.assertRaises(RuntimeError) as caught:
                step._produce(iter([fixtures.context()]), _FrameQueue(), Event())
        self.assertIs(caught.exception, first)
        self.assertEqual(stream.synchronize.call_count, 1)

    def test_pool_failure_does_not_trigger_native_work_in_final_reset(self):
        import test_nvidia_decode as fixtures
        from pipeworks.embedded.nvidia_decode import _FrameQueue

        case = fixtures.DecodeTests()
        self.addCleanup(case.doCleanups)
        step, api = case.setup_decoder(lambda packet: [])
        decoder = api.CreateDecoder()
        decoder.GetNumDecodedFrame = lambda packet: 1
        decoder.GetLockedFrame = Mock()
        decoder.UnlockFrame = Mock()
        api.CreateDecoder = lambda **kwargs: decoder
        pool = BufferCleanupTests().pool()
        event = BufferCleanupTests().event()
        first = RuntimeError("unlock failed")
        pool.locked.update((1, 2))
        pool.retired = [(1, event), (2, event)]
        pool.decoder.UnlockFrame.side_effect = [None, first]
        slot = _FrameQueue()
        slot.buffers = pool
        stream = SimpleNamespace(cuda_stream=1, synchronize=Mock())
        with patch("pipeworks.embedded.nvidia_decode.torch.cuda.Stream", return_value=stream):
            with self.assertRaises(RuntimeError) as caught:
                step._produce(iter([fixtures.context()]), slot, Event())
        self.assertIs(caught.exception, first)
        stream.synchronize.assert_not_called()
        pool.close()
        self.assertEqual(pool.decoder.UnlockFrame.call_args_list, [call(1), call(2)])


if __name__ == "__main__":
    unittest.main()
