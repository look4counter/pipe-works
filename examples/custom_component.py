from pipeworks import DetectionBoxOverlay, MockSource, Pipeline, PipelineContext, YoloInference


class CobbleFilter:
    def process(self, context: PipelineContext) -> PipelineContext:
        context.detections = [
            detection for detection in context.detections if detection.confidence >= 0.5
        ]
        return context


pipeline = (
    Pipeline("custom-cobble-filter")
    .source(MockSource("cam01"))
    .inference(YoloInference("models/cobble.engine"))
    .process(CobbleFilter())
    .overlay(DetectionBoxOverlay())
)


if __name__ == "__main__":
    print(pipeline.run().contexts[0].detections)
