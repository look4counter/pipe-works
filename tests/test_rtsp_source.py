import sys
import unittest
from threading import Event
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import av
from fractions import Fraction

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pipeworks.embedded.rtsp_source import RTSPSource


class Container:
    def __init__(self):
        self.stream = SimpleNamespace(
            codec_context=SimpleNamespace(name="h264", width=640, height=480,
                                          extradata=bytearray(b"header")),
            time_base=Fraction(1, 90000), index=0,
        )
        self.streams = SimpleNamespace(video=[self.stream])
        self.packets = [
            SimpleNamespace(size=2),
            SimpleNamespace(size=0),
            SimpleNamespace(size=3),
        ]
        self.closed = 0

    def demux(self, stream):
        self.requested_stream = stream
        yield from self.packets

    def close(self):
        self.closed += 1


class RTSPSourceTests(unittest.TestCase):
    def test_reconnect_interval_ms_waits_and_stop_event(self):
        for config, seconds in [
            ({}, 3),
            ({"reconnect_interval_ms": 0}, 0),
            ({"reconnect_interval_ms": 250}, 0.25),
            ({"reconnect_interval_ms": 1250.5}, 1.2505),
        ]:
            for use_stop in [False, True]:
                with self.subTest(config=config, use_stop=use_stop):
                    source = RTSPSource("rtsp://input")
                    source.configure(SimpleNamespace(**config))
                    if use_stop:
                        from unittest.mock import Mock

                        stop = Mock()
                        stop.is_set.side_effect = [False, True]
                        source._pipeworks_stop_event = stop
                    with (
                        patch(
                            "pipeworks.embedded.rtsp_source.av.open",
                            side_effect=[
                                av.error.FFmpegError(1, "failed"),
                                Container(),
                            ],
                        ),
                        patch("pipeworks.embedded.rtsp_source.time.sleep") as sleep,
                    ):
                        iterator = source.process(iter(()))
                        if use_stop:
                            self.assertEqual(list(iterator), [])
                            stop.wait.assert_called_once_with(seconds)
                            sleep.assert_not_called()
                        else:
                            next(iterator)
                            iterator.close()
                            sleep.assert_called_once_with(seconds)
                    self.assertEqual(
                        source.reconnect_interval_ms,
                        config.get("reconnect_interval_ms", 3000),
                    )

    def test_invalid_reconnect_interval_configuration(self):
        configs = [
            {"reconnect_interval_ms": value}
            for value in [-1, True, "3000", None, float("nan"), float("inf")]
        ]
        for config in configs:
            with (
                self.subTest(config=config),
                self.assertRaisesRegex(ValueError, "reconnect_interval_ms"),
            ):
                RTSPSource("rtsp://input").configure(SimpleNamespace(**config))

    def test_current_options_ignore_unused_legacy_keys(self):
        for config, interval_ms, timeout_ms in [
            ({"reconnect_interval": 99, "timeout": 99}, 3000, 5000),
            (
                {
                    "reconnect_interval": 99,
                    "timeout": 99,
                    "reconnect_interval_ms": 250,
                    "timeout_ms": 1250.5,
                },
                250,
                1250.5,
            ),
        ]:
            with self.subTest(config=config):
                source = RTSPSource("rtsp://input")
                source.configure(SimpleNamespace(**config))
                self.assertEqual(source.reconnect_interval_ms, interval_ms)
                self.assertEqual(source.timeout_ms, timeout_ms)

    def test_timeout_ms_conversion(self):
        for config, seconds in [
            ({}, 5),
            ({"timeout_ms": 0}, 0),
            ({"timeout_ms": 250}, 0.25),
            ({"timeout_ms": 1250.5}, 1.2505),
            ({"timeout_ms": 10000}, 10),
        ]:
            with self.subTest(config=config):
                source = RTSPSource("rtsp://input")
                source.configure(SimpleNamespace(**config))
                with patch(
                    "pipeworks.embedded.rtsp_source.av.open", return_value=Container()
                ) as opened:
                    iterator = source.process(iter(()))
                    next(iterator)
                    iterator.close()
                self.assertEqual(opened.call_args.kwargs["timeout"], (seconds, seconds))
                self.assertEqual(source.timeout_ms, config.get("timeout_ms", 5000))

    def test_invalid_timeout_configuration(self):
        configs = [
            {"timeout_ms": value}
            for value in [-1, True, "5000", None, float("nan"), float("inf")]
        ]
        for config in configs:
            with (
                self.subTest(config=config),
                self.assertRaisesRegex(ValueError, "timeout_ms"),
            ):
                RTSPSource("rtsp://input").configure(SimpleNamespace(**config))

    def test_valid_packets_and_generator_close(self):
        container = Container()
        source = RTSPSource("rtsp://input")
        source.configure(SimpleNamespace(reconnect=False))
        with (
            patch("pipeworks.embedded.rtsp_source.av.open", return_value=container),
            patch("pipeworks.embedded.rtsp_source.record_receive") as status,
        ):
            iterator = source.process(iter(()))
            first = next(iterator)
            second = next(iterator)
            iterator.close()
        self.assertEqual([call.args[0] for call in status.call_args_list], [True, True])
        self.assertIs(first.packet, container.packets[0])
        self.assertIs(second.packet, container.packets[2])
        self.assertIsNot(first.video_stream, container.stream)
        self.assertIs(first.video_stream, second.video_stream)
        self.assertEqual(first.video_stream.codec_context.extradata, b"header")
        self.assertEqual(container.closed, 1)

    def test_metadata_is_copied_once_for_thousand_packets(self):
        from pipeworks.video import VideoStreamInfo

        container = Container()
        container.packets = [SimpleNamespace(size=2) for _ in range(1000)]
        source = RTSPSource("rtsp://input", reconnect=False)
        with (
            patch("pipeworks.embedded.rtsp_source.av.open", return_value=container),
            patch("pipeworks.embedded.rtsp_source.VideoStreamInfo.from_stream",
                  wraps=VideoStreamInfo.from_stream) as snapshot,
        ):
            iterator = source.process(iter(()))
            items = [next(iterator) for _ in range(1000)]
            iterator.close()
        snapshot.assert_called_once_with(container.stream)
        container.stream.codec_context.extradata[0] = 0
        container.stream.codec_context = None
        self.assertEqual(len({id(item.video_stream) for item in items}), 1)
        self.assertEqual(items[-1].video_stream.codec_context.extradata, b"header")

    def test_identical_reconnection_has_new_metadata_identity(self):
        first, second = Container(), Container()
        source = RTSPSource("rtsp://input", reconnect_interval_ms=0)
        with patch("pipeworks.embedded.rtsp_source.av.open", side_effect=[first, second]):
            iterator = source.process(iter(()))
            old = next(iterator).video_stream
            next(iterator)
            new = next(iterator).video_stream
            iterator.close()
        self.assertEqual(first.closed, 1)
        self.assertNotEqual(old.connection_id, new.connection_id)
        self.assertEqual(old.codec_context, new.codec_context)

    def test_connection_error_retries_even_when_reconnect_disabled(self):
        container = Container()
        source = RTSPSource("rtsp://input")
        source.configure(SimpleNamespace(reconnect_interval_ms=0))
        error = av.error.FFmpegError(1, "failed")
        with (
            patch(
                "pipeworks.embedded.rtsp_source.av.open", side_effect=[error, container]
            ) as open_mock,
            patch("pipeworks.embedded.rtsp_source.time.sleep"),
            patch("pipeworks.embedded.rtsp_source.record_receive") as status,
        ):
            iterator = source.process(iter(()))
            first = next(iterator)
            iterator.close()
        self.assertEqual(
            [call.args[0] for call in status.call_args_list], [False, True]
        )
        self.assertIs(first.packet, container.packets[0])
        self.assertEqual(open_mock.call_count, 2)
        self.assertEqual(container.closed, 1)

        stopped = RTSPSource("rtsp://input", reconnect=False, reconnect_interval_ms=0)
        with (
            patch("pipeworks.embedded.rtsp_source.av.open", side_effect=[error, Container()]),
            patch("pipeworks.embedded.rtsp_source.time.sleep"),
        ):
            iterator = stopped.process(iter(()))
            next(iterator)
            iterator.close()

    def test_invalid_metadata_reopens_before_delivering_packets(self):
        cases = [
            ("missing_video", None), ("missing_codec", None),
            ("name", ""), ("name", "  "), ("name", None), ("name", 123),
            ("width", 0), ("width", -1), ("height", 0), ("height", -1),
            ("width", None), ("width", True), ("height", 64.5),
            ("extradata", "invalid"),
            ("time_base", 0), ("time_base", -1), ("time_base", "invalid"),
            ("average_rate", 0), ("average_rate", -1),
            ("index", -1), ("index", None),
        ]
        for reconnect in (True, False):
            for field, value in cases:
                with self.subTest(reconnect=reconnect, field=field, value=value):
                    bad, good = Container(), Container()
                    if field == "missing_video":
                        bad.streams.video = []
                    elif field == "missing_codec":
                        bad.stream.codec_context = None
                    else:
                        target = (bad.stream if field in (
                            "time_base", "average_rate", "index",
                        ) else bad.stream.codec_context)
                        setattr(target, field, value)
                    bad.demux = Mock(side_effect=AssertionError("invalid packets"))
                    source = RTSPSource("rtsp://input", reconnect=reconnect,
                                        reconnect_interval_ms=250)

                    def opened(*args, **kwargs):
                        if bad.closed:
                            return good
                        return bad

                    def waited(seconds):
                        self.assertEqual(seconds, 0.25)
                        self.assertEqual(bad.closed, 1)

                    with (
                        patch("pipeworks.embedded.rtsp_source.av.open",
                              side_effect=opened) as open_mock,
                        patch("pipeworks.embedded.rtsp_source.time.sleep",
                              side_effect=waited) as sleep,
                        patch("pipeworks.embedded.rtsp_source.record_receive") as status,
                        self.assertLogs("pipeworks.embedded.rtsp_source", "WARNING"),
                    ):
                        iterator = source.process(iter(()))
                        try:
                            first = next(iterator)
                        finally:
                            iterator.close()
                    self.assertIs(first.packet, good.packets[0])
                    self.assertEqual(first.video_stream.width, 640)
                    self.assertEqual(open_mock.call_count, 2)
                    sleep.assert_called_once_with(0.25)
                    bad.demux.assert_not_called()
                    self.assertEqual((bad.closed, good.closed), (1, 1))
                    self.assertEqual([c.args[0] for c in status.call_args_list],
                                     [False, True])

    def test_repeated_invalid_connections_resume_with_new_metadata(self):
        first, bad, bad_again, recovered = [Container() for _ in range(4)]
        bad.stream.codec_context.width = 0
        bad_again.stream.codec_context.name = ""
        source = RTSPSource("rtsp://input", reconnect_interval_ms=0)
        with (
            patch("pipeworks.embedded.rtsp_source.av.open",
                  side_effect=[first, bad, bad_again, recovered]) as opened,
            patch("pipeworks.embedded.rtsp_source.time.sleep") as sleep,
            self.assertLogs("pipeworks.embedded.rtsp_source", "WARNING"),
        ):
            iterator = source.process(iter(()))
            try:
                old = next(iterator).video_stream
                next(iterator)
                new = next(iterator).video_stream
            finally:
                iterator.close()
        self.assertNotEqual(old.connection_id, new.connection_id)
        self.assertEqual(old.codec_context, new.codec_context)
        self.assertEqual(opened.call_count, 4)
        self.assertEqual(sleep.call_count, 3)
        self.assertTrue(all(c.closed == 1 for c in (first, bad, bad_again, recovered)))

    def test_metadata_retry_can_be_stopped_or_cancelled(self):
        from pipeworks.execution import _source_cancel_scope

        for signal_kind in ("stop", "cancel"):
            with self.subTest(signal=signal_kind):
                bad = Container()
                bad.stream.codec_context.width = 0
                source = RTSPSource("rtsp://input", reconnect_interval_ms=250)
                signal = Event()
                if signal_kind == "stop":
                    source._pipeworks_stop_event = signal

                def interrupt(seconds):
                    self.assertEqual(bad.closed, 1)
                    signal.set()
                    return True

                with (
                    _source_cancel_scope(signal if signal_kind == "cancel" else None),
                    patch("pipeworks.embedded.rtsp_source.av.open",
                          return_value=bad) as opened,
                    patch.object(signal, "wait", side_effect=interrupt) as wait,
                    patch("pipeworks.embedded.rtsp_source.time.sleep") as sleep,
                    self.assertLogs("pipeworks.embedded.rtsp_source", "WARNING"),
                ):
                    self.assertEqual(list(source.process(iter(()))), [])
                opened.assert_called_once()
                self.assertEqual(wait.call_count, 1)
                self.assertEqual(bad.closed, 1)
                sleep.assert_not_called()

    def test_demux_value_error_reconnects(self):
        bad, good = Container(), Container()
        bad.demux = Mock(side_effect=ValueError("demux failed"))
        with (
            patch("pipeworks.embedded.rtsp_source.av.open", side_effect=[bad, good]),
            patch("pipeworks.embedded.rtsp_source.time.sleep") as sleep,
        ):
            iterator = RTSPSource("rtsp://input").process(iter(()))
            first = next(iterator)
            iterator.close()
        self.assertIs(first.packet, good.packets[0])
        sleep.assert_called_once_with(3)
        self.assertEqual(bad.closed, 1)

    def test_stream_end_reconnects_even_when_reconnect_disabled(self):
        first, second = Container(), Container()
        with (
            patch("pipeworks.embedded.rtsp_source.av.open", side_effect=[first, second]),
            patch("pipeworks.embedded.rtsp_source.time.sleep"),
        ):
            iterator = RTSPSource("rtsp://input", reconnect=False).process(iter(()))
            next(iterator)
            next(iterator)
            self.assertIs(next(iterator).packet, second.packets[0])
            iterator.close()
        self.assertEqual(first.closed, 1)


if __name__ == "__main__":
    unittest.main()
