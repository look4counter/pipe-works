import pytest

from pipeworks import MockSource, Pipeline, Stream


def test_validate_reports_missing_input_without_running() -> None:
    report = Pipeline("empty").validate()

    assert report.valid is False
    assert "source(...)" in report.errors[0]


def test_run_fails_early_for_ambiguous_input() -> None:
    with pytest.raises(ValueError, match="both source.*streams"):
        (
            Pipeline("ambiguous")
            .source(MockSource("cam01"))
            .streams([Stream("cam01", source="rtsp://cam01")])
            .run()
        )


def test_validate_reports_duplicate_stream_ids() -> None:
    report = Pipeline("duplicates").streams(
        [Stream("cam01", source="rtsp://one"), Stream("cam01", source="rtsp://two")]
    ).validate()

    assert report.valid is False
    assert "cam01" in report.errors[0]


def test_output_is_a_warning_for_analysis_only_pipeline() -> None:
    report = Pipeline("analysis").source(MockSource("cam01")).validate()

    assert report.valid is True
    assert report.warnings == ("pipeline has no output(...); results will remain in memory",)
