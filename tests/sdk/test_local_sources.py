from pipeworks import FileSource, Pipeline, SyntheticSource, YoloInference


def test_synthetic_source_runs_without_external_video() -> None:
    result = (
        Pipeline("synthetic")
        .source(SyntheticSource("sim", frame_count=3, width=320, height=180))
        .inference(YoloInference("models/fake.engine"))
        .run()
    )

    assert [context.frame.sequence for context in result.contexts] == [0, 1, 2]
    assert result.contexts[0].frame.metadata["width"] == 320


def test_file_source_runs_as_local_descriptor() -> None:
    result = Pipeline("file").source(FileSource("samples/cobble.mp4")).run()

    assert result.contexts[0].stream_id == "file"
    assert result.contexts[0].frame.metadata["path"] == "samples/cobble.mp4"
