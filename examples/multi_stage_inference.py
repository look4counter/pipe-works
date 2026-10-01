from pipeworks import (
    DetectionBoxOverlay,
    DetectionCrop,
    Pipeline,
    RTSPPublisher,
    RTSPSource,
    YoloInference,
)

pipeline = (
    Pipeline("cobble-multistage")
    .source(RTSPSource("rtsp://camera/main"))
    .inference(YoloInference("models/primary.engine", stage="primary"))
    .transform(DetectionCrop())
    .inference(YoloInference("models/secondary.engine", stage="secondary"))
    .overlay(DetectionBoxOverlay())
    .output(RTSPPublisher("rtsp://mediamtx/result"))
)


if __name__ == "__main__":
    result = pipeline.run()
    print(result.contexts[0].results.keys())
