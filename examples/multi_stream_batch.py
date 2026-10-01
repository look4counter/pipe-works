from pipeworks import DetectionBoxOverlay, Pipeline, Stream, YoloInference

pipeline = (
    Pipeline("cobble-9ch")
    .streams(
        [
            Stream("cam01", source="rtsp://cam01", output="rtsp://mediamtx/cam01"),
            Stream("cam02", source="rtsp://cam02", output="rtsp://mediamtx/cam02"),
            Stream("cam03", source="rtsp://cam03", output="rtsp://mediamtx/cam03"),
            Stream("cam04", source="rtsp://cam04", output="rtsp://mediamtx/cam04"),
            Stream("cam05", source="rtsp://cam05", output="rtsp://mediamtx/cam05"),
            Stream("cam06", source="rtsp://cam06", output="rtsp://mediamtx/cam06"),
            Stream("cam07", source="rtsp://cam07", output="rtsp://mediamtx/cam07"),
            Stream("cam08", source="rtsp://cam08", output="rtsp://mediamtx/cam08"),
            Stream("cam09", source="rtsp://cam09", output="rtsp://mediamtx/cam09"),
        ]
    )
    .batch_inference(YoloInference("models/cobble.engine"))
    .overlay(DetectionBoxOverlay())
)


if __name__ == "__main__":
    result = pipeline.run()
    print([context.stream_id for context in result.contexts])
