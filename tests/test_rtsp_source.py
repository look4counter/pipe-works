import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import av

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pipeworks.embedded.rtsp_source import RTSPSource


class Container:
    def __init__(self):
        self.stream = object()
        self.streams = SimpleNamespace(video=[self.stream])
        self.packets = [SimpleNamespace(size=2), SimpleNamespace(size=0), SimpleNamespace(size=3)]
        self.closed = 0

    def demux(self, stream):
        self.requested_stream = stream
        yield from self.packets

    def close(self):
        self.closed += 1


class RTSPSourceTests(unittest.TestCase):
    def test_reconnect_interval_ms_waits_and_stop_event(self):
        for config, seconds in [({}, 3), ({"reconnect_interval_ms": 0}, 0), ({"reconnect_interval_ms": 250}, .25), ({"reconnect_interval_ms": 1250.5}, 1.2505)]:
            for use_stop in [False, True]:
                with self.subTest(config=config, use_stop=use_stop):
                    source = RTSPSource("rtsp://input")
                    source.configure(SimpleNamespace(**config))
                    if use_stop:
                        from unittest.mock import Mock
                        stop = Mock()
                        stop.is_set.side_effect = [False, True]
                        source._pipeworks_stop_event = stop
                    with patch("pipeworks.embedded.rtsp_source.av.open", side_effect=[av.error.FFmpegError(1, "failed"), Container()]), patch("pipeworks.embedded.rtsp_source.time.sleep") as sleep:
                        iterator = source.process(iter(()))
                        if use_stop:
                            self.assertEqual(list(iterator), [])
                            stop.wait.assert_called_once_with(seconds)
                            sleep.assert_not_called()
                        else:
                            next(iterator)
                            iterator.close()
                            sleep.assert_called_once_with(seconds)
                    self.assertEqual(source.reconnect_interval_ms, config.get("reconnect_interval_ms", 3000))

    def test_invalid_reconnect_interval_configuration(self):
        configs = [{"reconnect_interval_ms": value} for value in [-1, True, "3000", None, float("nan"), float("inf")]]
        configs += [{"reconnect_interval": 3}, {"reconnect_interval": 3, "reconnect_interval_ms": 3000}]
        for config in configs:
            with self.subTest(config=config), self.assertRaisesRegex(ValueError, "reconnect_interval_ms"):
                RTSPSource("rtsp://input").configure(SimpleNamespace(**config))

    def test_timeout_ms_conversion(self):
        for config, seconds in [({}, 5), ({"timeout_ms": 0}, 0), ({"timeout_ms": 250}, .25), ({"timeout_ms": 1250.5}, 1.2505), ({"timeout_ms": 10000}, 10)]:
            with self.subTest(config=config):
                source = RTSPSource("rtsp://input")
                source.configure(SimpleNamespace(**config))
                with patch("pipeworks.embedded.rtsp_source.av.open", return_value=Container()) as opened:
                    iterator = source.process(iter(()))
                    next(iterator)
                    iterator.close()
                self.assertEqual(opened.call_args.kwargs["timeout"], (seconds, seconds))
                self.assertEqual(source.timeout_ms, config.get("timeout_ms", 5000))

    def test_invalid_timeout_configuration(self):
        configs = [{"timeout_ms": value} for value in [-1, True, "5000", None, float("nan"), float("inf")]]
        configs += [{"timeout": 5}, {"timeout": 5, "timeout_ms": 5000}]
        for config in configs:
            with self.subTest(config=config), self.assertRaisesRegex(ValueError, "timeout_ms"):
                RTSPSource("rtsp://input").configure(SimpleNamespace(**config))

    def test_valid_packets_and_generator_close(self):
        container = Container()
        source = RTSPSource("rtsp://input")
        source.configure(SimpleNamespace(reconnect=False))
        with patch("pipeworks.embedded.rtsp_source.av.open", return_value=container), patch(
            "pipeworks.embedded.rtsp_source.record_receive"
        ) as status:
            iterator = source.process(iter(()))
            first = next(iterator)
            second = next(iterator)
            iterator.close()
        self.assertEqual([call.args[0] for call in status.call_args_list], [True, True])
        self.assertIs(first.packet, container.packets[0])
        self.assertIs(second.packet, container.packets[2])
        self.assertIs(first.video_stream, container.stream)
        self.assertEqual(container.closed, 1)

    def test_connection_error_retries_and_disabled_reconnect_raises(self):
        container = Container()
        source = RTSPSource("rtsp://input")
        source.configure(SimpleNamespace(reconnect_interval_ms=0))
        error = av.error.FFmpegError(1, "failed")
        with patch("pipeworks.embedded.rtsp_source.av.open", side_effect=[error, container]) as open_mock, patch(
            "pipeworks.embedded.rtsp_source.time.sleep"
        ), patch("pipeworks.embedded.rtsp_source.record_receive") as status:
            iterator = source.process(iter(()))
            first = next(iterator)
            iterator.close()
        self.assertEqual([call.args[0] for call in status.call_args_list], [False, True])
        self.assertIs(first.packet, container.packets[0])
        self.assertEqual(open_mock.call_count, 2)
        self.assertEqual(container.closed, 1)

        stopped = RTSPSource("rtsp://input")
        stopped.configure(SimpleNamespace(reconnect=False))
        with patch("pipeworks.embedded.rtsp_source.av.open", side_effect=error):
            with self.assertRaises(RuntimeError):
                next(stopped.process(iter(())))

    def test_missing_video_stream_fails_and_closes(self):
        container = Container()
        container.streams.video = []
        source = RTSPSource("rtsp://input")
        source.configure(SimpleNamespace())
        with patch("pipeworks.embedded.rtsp_source.av.open", return_value=container):
            with self.assertRaises(RuntimeError):
                next(source.process(iter(())))
        self.assertEqual(container.closed, 1)

    def test_stream_end_with_reconnect_disabled_stops_pipeline(self):
        container = Container()
        source = RTSPSource("rtsp://input")
        source.configure(SimpleNamespace(reconnect=False))
        with patch("pipeworks.embedded.rtsp_source.av.open", return_value=container):
            iterator = source.process(iter(()))
            next(iterator)
            next(iterator)
            with self.assertRaises(RuntimeError):
                next(iterator)
        self.assertEqual(container.closed, 1)


if __name__ == "__main__":
    unittest.main()
