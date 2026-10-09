from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from pipeworks import Pipeline
from pipeworks.embedded import (
    RTSPSource,
    RTSPPublish,
    NvidiaEncode,
    NvidiaDecode,
    StreamReport,
    Tap,
)
from pipeworks.embedded.yolo_detect_batch import YoloDetectBatch
from step.box_overlay import BoxOverlay
from step.metadata_from_db import MetadataFromDB
from step.post_process import PostProcess


def build_pipeline(video: str) -> Pipeline:
    return (
        Pipeline(
            f"cobble-detection-{video}",
            config=Path(__file__).with_name("config") / "stream.yml",
        )
        .step(RTSPSource(f"rtsp://210.99.70.120:1935/live/{video}.stream"))
        .step(NvidiaDecode())
        .step(MetadataFromDB())
        .step(YoloDetectBatch(Path(__file__).with_name("model") / "yolo11n.engine"))
        .step(BoxOverlay())
        .step(NvidiaEncode())
        .step(Tap(PostProcess()))
        .step(RTSPPublish(f"rtsp://localhost:8554/{video}"))
        .step(StreamReport())
    )


def run_pipelines(videos: tuple[str, ...]) -> None:
    pipelines = [build_pipeline(video) for video in videos]
    with ThreadPoolExecutor(max_workers=len(pipelines)) as executor:
        futures = [executor.submit(pipeline.run) for pipeline in pipelines]
        for future in futures:
            future.result()


if __name__ == "__main__":
    run_pipelines(("cctv001", "cctv002", "cctv003", "cctv004", "cctv005"))
