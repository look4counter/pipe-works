from pipeworks import DetectionBoxOverlay, Pipeline, PipelineContext, SyntheticSource, YoloInference


class CobbleFilter:
    def process(self, context: PipelineContext) -> PipelineContext:
        context.detections = [
            detection for detection in context.detections if detection.confidence >= 0.5
        ]
        return context


pipeline = (
    Pipeline("custom-cobble-filter")
    .source(SyntheticSource("sim-cam", frame_count=2))
    .inference(YoloInference("models/cobble.engine"))
    .process(CobbleFilter())
    .overlay(DetectionBoxOverlay())
)


if __name__ == "__main__":
    result = pipeline.run()
    print([context.detections for context in result.contexts])
