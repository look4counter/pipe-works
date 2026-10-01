"""Starter templates for SDK users."""

STARTER_PIPELINE = '''from pipeworks import DetectionBoxOverlay, Pipeline, RTSPPublisher, SyntheticSource, YoloInference


def build_pipeline() -> Pipeline:
    return (
        Pipeline("starter-cobble", config="pipeworks.yaml")
        # What: 영상 입력과 모델 정체성은 Python에서 읽는다.
        .source(SyntheticSource("local-cam", frame_count=3))
        .inference(YoloInference("models/cobble.engine"))
        .overlay(DetectionBoxOverlay())
        .output(RTSPPublisher("memory://starter-output"))
    )


if __name__ == "__main__":
    pipeline = build_pipeline()
    print(pipeline.diagram())
    result = pipeline.run()
    for context in result.contexts:
        detection_result = context.results["YoloInference"]
        print(
            context.stream_id,
            context.frame.sequence,
            len(detection_result.detections),
        )
    print(result.metrics.to_json())
'''


STARTER_CONFIG = """Pipeline:
  queue_size: 4
  drop_policy: drop_oldest

YoloInference:
  confidence: 0.7
  device: cpu

Realtime:
  max_end_to_end_latency_ms: 1000
  max_frame_age_ms: 800
  drop_expired_frames: true
  output_latency_action: drop
"""
