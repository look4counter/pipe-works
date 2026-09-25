from types import SimpleNamespace
from threading import Event
from unittest.mock import Mock

from pipeline import receive as receive_module
from pipeline.arguments import PipelineArguments


def parameters() -> PipelineArguments:
    return PipelineArguments(
        "rtsp://camera/input", "tcp", "rtsp://server/output", "udp", "nvidia", 0,
        False, None, False, None, 3, None, False, None,
    )


def test_receive_yields_video_packets_and_closes_container(monkeypatch) -> None:
    video_stream = object()
    packets = [SimpleNamespace(size=0), SimpleNamespace(size=12)]
    container = Mock()
    container.streams.video = [video_stream]
    container.demux.return_value = iter(packets)
    monkeypatch.setattr(receive_module.av, "open", Mock(return_value=container))

    received = receive_module.receive(parameters())
    result = next(received)
    received.close()

    assert result.video_stream is video_stream
    assert result.data is packets[1]
    container.demux.assert_called_once_with(video_stream)
    container.close.assert_called_once_with()


def test_receive_stops_after_stop_event_and_closes_container(monkeypatch) -> None:
    video_stream = object()
    container = Mock()
    container.streams.video = [video_stream]
    container.demux.return_value = iter([SimpleNamespace(size=12)])
    monkeypatch.setattr(receive_module.av, "open", Mock(return_value=container))
    stop_event = Event()

    received = receive_module.receive(parameters(), stop_event)
    assert next(received).video_stream is video_stream
    stop_event.set()

    assert list(received) == []
    container.close.assert_called_once_with()


def test_receive_retries_after_ffmpeg_error(monkeypatch) -> None:
    class FakeFFmpegError(Exception):
        pass

    attempts = 0

    def open_container(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise FakeFFmpegError()
        container = Mock()
        container.streams.video = [object()]
        container.demux.return_value = iter([SimpleNamespace(size=1)])
        return container

    monkeypatch.setattr(receive_module.av.error, "FFmpegError", FakeFFmpegError)
    monkeypatch.setattr(receive_module.av, "open", open_container)
    monkeypatch.setattr(receive_module.time, "sleep", lambda _: None)

    received = receive_module.receive(parameters())
    assert next(received).data.size == 1
    received.close()
    assert attempts == 2
