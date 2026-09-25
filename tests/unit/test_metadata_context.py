from pipeline.cli import attach_metadata
from pipeline.context import FrameContext


def frame() -> FrameContext:
    return FrameContext(video_stream=object(), data=object())


def test_attach_metadata_uses_latest_value_for_each_frame() -> None:
    first_frame, second_frame = frame(), frame()
    first_metadata = {"version": 1}
    second_metadata = {"version": 2}
    module_state = {"metadata": first_metadata}
    frames = attach_metadata(iter([first_frame, second_frame]), module_state)

    assert next(frames).metadata is first_metadata
    module_state["metadata"] = second_metadata
    assert next(frames).metadata is second_metadata


def test_attach_metadata_leaves_none_when_no_metadata_is_loaded() -> None:
    decoded_frame = frame()

    result = next(attach_metadata(iter([decoded_frame]), {}))

    assert result.metadata is None
