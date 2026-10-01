from pipeworks import Frame, Pipeline


class FlakySource:
    name = "RTSPSource"

    def __init__(self) -> None:
        self.calls = 0

    def frames(self):
        self.calls += 1
        if self.calls < 2:
            raise ConnectionError("camera unavailable")
        return [Frame("cam01", image="reconnected")]


def test_source_worker_reconnects_without_exposing_loop_to_user(tmp_path) -> None:
    config = tmp_path / "pipeworks.yaml"
    config.write_text(
        "RTSPSource:\n  reconnect: true\n  reconnect_attempts: 2\n  reconnect_interval: 0\n",
        encoding="utf-8",
    )
    source = FlakySource()

    result = Pipeline("reconnect", config=config).source(source).run()

    assert source.calls == 2
    assert result.contexts[0].frame.image == "reconnected"
