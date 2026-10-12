from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from pipeworks import Backend, Pipeline
from pipeworks.embedded import (
    RTSPSource,
    RTSPPublish,
    NvidiaEncode,
    NvidiaDecode,
    StreamReport,
    TapSkipIfBusy,
)
from pipeworks.embedded import YoloInference
from step.yolo_pre_process import YoloPreProcess
from step.yolo_post_process import YoloPostProcess
from step.box_overlay import BoxOverlay
from step.metadata_from_db import MetadataFromDB
from step.save_inference_result_to_db import SaveInferenceResultToDB


def build_pipeline(video: str) -> Pipeline:
    return (
        Pipeline(
            f"cobble-detection-{video}",
            config=Path(__file__).with_name("config") / "stream.yml",
        )
        .step(RTSPSource(f"rtsp://210.99.70.120:1935/live/{video}.stream"))
        .step(NvidiaDecode())
        .step(MetadataFromDB())
        .step(YoloPreProcess())
        .step(
            YoloInference(
                Path(__file__).with_name("model") / "yolo11n.engine",
                backend=Backend.TENSORRT, batch=True,
            )
        )
        .step(YoloPostProcess())
        .step(BoxOverlay())
        .step(NvidiaEncode())
        .step(TapSkipIfBusy(SaveInferenceResultToDB()))
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
