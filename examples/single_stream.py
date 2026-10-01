from pipeworks import (
    DetectionBoxOverlay,
    MQPublishAction,
    Pipeline,
    RTSPPublisher,
    RTSPSource,
    StaticBoxOverlay,
    SvgSendAction,
    YoloInference,
)

pipeline = (
    Pipeline("cobble-detection")
    .source(RTSPSource("rtsp://camera/main"))
    .inference(YoloInference("models/cobble.engine"))
    .overlay(StaticBoxOverlay())
    .overlay(DetectionBoxOverlay())
    .action(SvgSendAction("http://server/api/svg"))
    .action(MQPublishAction("cobble.detected"))
    .output(RTSPPublisher("rtsp://mediamtx/cobble"))
)


if __name__ == "__main__":
    result = pipeline.run()
    print(pipeline.describe())
    print(result.metrics)
