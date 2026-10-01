"""Starter templates for SDK users."""

STARTER_PIPELINE = '''from pipeworks import DetectionBoxOverlay, Pipeline, SyntheticSource, YoloInference


pipeline = (
    Pipeline("starter-cobble", config="pipeworks.yaml")
    .source(SyntheticSource("local-cam", frame_count=3))
    .inference(YoloInference("models/cobble.engine"))
    .overlay(DetectionBoxOverlay())
)


if __name__ == "__main__":
    print(pipeline.diagram())
    print(pipeline.run().metrics)
'''


STARTER_CONFIG = """Pipeline:
  queue_size: 4
  drop_policy: drop_oldest

YoloInference:
  confidence: 0.7
  device: cpu
"""
