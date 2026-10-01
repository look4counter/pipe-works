from pathlib import Path

from pipeworks import DetectionBoxOverlay, Pipeline, SyntheticSource, YoloInference

config_path = Path(__file__).with_name("local_pipeline.yaml")

pipeline = (
    Pipeline("local-configured-pipeline", config=config_path)
    .source(SyntheticSource("local-cam", frame_count=3, width=320, height=180))
    .inference(YoloInference("models/local.engine"))
    .overlay(DetectionBoxOverlay())
)


if __name__ == "__main__":
    result = pipeline.run()
    print(result.metrics)
    print([context.detections[0].confidence for context in result.contexts])
