"""예제 04: SDK를 수정하지 않고 도메인 규칙을 Component로 추가한다."""

from pipeworks import DetectionBoxOverlay, Pipeline, PipelineContext, SyntheticSource, YoloInference


class CobbleFilter:
    """신뢰도가 낮은 Detection을 제거하는 사용자 정의 Processor."""

    def process(self, context: PipelineContext) -> PipelineContext:
        # Context에는 최신 Inference 결과가 detections로 노출된다.
        context.detections = [
            detection for detection in context.detections if detection.confidence >= 0.5
        ]
        return context


pipeline = (
    Pipeline("custom-cobble-filter")
    .source(SyntheticSource("sim-cam", frame_count=2))
    .inference(YoloInference("models/cobble.engine"))
    # process()는 기존 SDK Component와 같은 위치에 자연스럽게 삽입된다.
    .process(CobbleFilter())
    .overlay(DetectionBoxOverlay())
)


if __name__ == "__main__":
    result = pipeline.run()
    print("필터링된 Detection:", [context.detections for context in result.contexts])
