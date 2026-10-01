import pytest

from pipeworks import Frame, PipelineContext, YoloInference
from pipeworks.adapters.actions import (
    ActionAdapterUnavailableError,
    HttpPostAction,
    MQAdapterAction,
)
from pipeworks.adapters.outputs import MediaMTXPublisher


def context_with_detection() -> PipelineContext:
    context = PipelineContext(Frame("cam01", sequence=3))
    context.add_result(YoloInference("models/fake.engine").infer(context, {"confidence": 0.75}))
    return context


def test_http_post_action_builds_detection_payload() -> None:
    action = HttpPostAction("http://example.test/events")
    payload = action.build_payload(context_with_detection())

    assert payload["stream_id"] == "cam01"
    assert payload["sequence"] == 3
    assert payload["detections"][0]["confidence"] == 0.75


def test_mq_adapter_reports_missing_dependency_when_unavailable() -> None:
    action = MQAdapterAction("cobble.detected")
    if action.available:
        pytest.skip("pika is installed in this environment")

    with pytest.raises(ActionAdapterUnavailableError, match="pika"):
        action.execute(context_with_detection(), {})


def test_mediatx_publisher_preserves_output_url() -> None:
    output = MediaMTXPublisher("rtsp://mediamtx/cam01")
    context = context_with_detection()

    output.write(context, {})

    assert output.written == [context]
    assert context.frame.metadata["output_url"] == "rtsp://mediamtx/cam01"
