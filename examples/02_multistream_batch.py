from pipeworks import DetectionBoxOverlay, Pipeline, Stream, YoloInference

pipeline = (
    Pipeline("cobble-9ch")
    .streams(
        [
            Stream(f"cam{index:02}", source=f"rtsp://cam{index:02}", output=f"rtsp://out/cam{index:02}")
            for index in range(1, 10)
        ]
    )
    .batch_inference(YoloInference("models/cobble.engine"))
    .overlay(DetectionBoxOverlay())
)


if __name__ == "__main__":
    result = pipeline.run()
    print([context.stream_id for context in result.contexts])
    print(result.metrics)
