from pathlib import Path
from time import perf_counter

from pipeworks import (
    Detection,
    DetectionBoxOverlay,
    DetectionCrop,
    MockSource,
    Pipeline,
    PipelineContext,
    RTSPPublisher,
    RTSPSource,
    StaticBoxOverlay,
    Stream,
    SvgSendAction,
    YoloInference,
)


def test_single_stream_dsl_describes_architecture_and_runs() -> None:
    output = RTSPPublisher("rtsp://mediamtx/cobble")

    pipeline = (
        Pipeline("cobble")
        .source(RTSPSource("rtsp://camera/main"))
        .inference(YoloInference("models/cobble.engine"))
        .overlay(StaticBoxOverlay())
        .overlay(DetectionBoxOverlay())
        .output(output)
    )

    description = "\n".join(pipeline.describe())
    result = pipeline.run()

    assert "RTSPSource(url=rtsp://camera/main" in description
    assert "YoloInference(model=models/cobble.engine)" in description
    assert "RTSPPublisher(url=rtsp://mediamtx/cobble)" in description
    assert result.metrics.frames_processed == 1
    assert result.metrics.output_count == 1
    assert output.written[0].stream_id == "default"


def test_yaml_overrides_behavior_without_hiding_identity(tmp_path: Path) -> None:
    config_path = tmp_path / "pipeworks.yaml"
    config_path.write_text(
        """
YoloInference:
  confidence: 0.8
""".strip(),
        encoding="utf-8",
    )

    pipeline = (
        Pipeline("configured", config=config_path)
        .source(MockSource("cam01"))
        .inference(YoloInference("models/cobble.engine"))
    )

    result = pipeline.run()

    assert result.contexts[0].detections[0].confidence == 0.8
    assert "models/cobble.engine" in "\n".join(pipeline.describe())


def test_multi_stream_batch_preserves_stream_identity() -> None:
    streams = [
        Stream("cam01", source="rtsp://cam01", output="rtsp://out01"),
        Stream("cam02", source="rtsp://cam02", output="rtsp://out02"),
        Stream("cam03", source="rtsp://cam03", output="rtsp://out03"),
    ]

    result = (
        Pipeline("batch")
        .streams(streams)
        .batch_inference(YoloInference("models/cobble.engine"))
        .overlay(DetectionBoxOverlay())
        .run()
    )

    assert [context.stream_id for context in result.contexts] == ["cam01", "cam02", "cam03"]
    for context in result.contexts:
        assert context.detections
        assert next(iter(context.results.values())).stream_id == context.stream_id
        assert context.overlays


def test_multistage_inference_keeps_stage_results() -> None:
    result = (
        Pipeline("multistage")
        .source(MockSource("cam01"))
        .inference(YoloInference("models/primary.engine", stage="primary"))
        .transform(DetectionCrop())
        .inference(YoloInference("models/secondary.engine", stage="secondary"))
        .run()
    )

    context = result.contexts[0]
    assert set(context.results) == {"primary", "secondary"}
    assert context.data["crops"]


def test_custom_processor_can_modify_context() -> None:
    class HighConfidenceOnly:
        def process(self, context: PipelineContext) -> PipelineContext:
            context.detections = [
                Detection(
                    box=detection.box,
                    confidence=0.95,
                    class_id=detection.class_id,
                    label=detection.label,
                )
                for detection in context.detections
            ]
            return context

    result = (
        Pipeline("custom")
        .source(MockSource("cam01"))
        .inference(YoloInference("models/cobble.engine"))
        .process(HighConfidenceOnly())
        .run()
    )

    assert result.contexts[0].detections[0].confidence == 0.95


def test_actions_are_scheduled_off_the_output_path() -> None:
    slow_action = SvgSendAction("http://server/api/svg", delay_s=0.2)
    output = RTSPPublisher("rtsp://mediamtx/cobble")

    pipeline = (
        Pipeline("async-action")
        .source(MockSource("cam01"))
        .inference(YoloInference("models/cobble.engine"))
        .action(slow_action)
        .output(output)
    )

    started = perf_counter()
    result = pipeline.run(wait_for_actions=False)
    elapsed = perf_counter() - started

    assert output.written
    assert result.metrics.actions_scheduled == 1
    assert elapsed < 0.1
