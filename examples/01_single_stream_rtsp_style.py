from pathlib import Path
from pipeworks import Pipeline
from pipeworks.embedded import (
    RTSPSource,
    RTSPPublish,
    NvidiaEncode,
    NvidiaDecode,
    StreamReport,
    Tap,
    Async,
)
from pipeworks.embedded.yolo_detect import YoloDetect
from step.box_overlay import BoxOverlay
from step.metadata_from_db import MetadataFromDB
from step.post_process import PostProcess


def build_pipeline() -> Pipeline:
    return (
        Pipeline(
            "cobble-detection",
            config=Path(__file__).with_name("config") / "stream.yml",
        )
        .step(RTSPSource("rtsp://210.99.70.120:1935/live/cctv001.stream"))
        .step(NvidiaDecode())
        .step(MetadataFromDB())
        .step(Async(YoloDetect(Path(__file__).with_name("model") / "yolo11n.pt"), timeout_ms=20))
        .step(BoxOverlay())
        .step(Tap(PostProcess()))
        .step(NvidiaEncode())
        .step(RTSPPublish("rtsp://localhost:8554/cctv001"))
        .step(StreamReport())
    )


if __name__ == "__main__":
    pipeline = build_pipeline()
    pipeline.run()
