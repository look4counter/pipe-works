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
from pipeworks.embedded.tensor_rt_inference import TensorRTInference
from pipeworks.embedded.yolo_detect import YoloDetect
from step.metadata_from_db import MetadataFromDB
from step.box_overlay import BoxOverlay
from step.save_inference_result_to_db import SaveInferenceResultToDB
from step.tensor_rt_pre_process import TensorRTPreProcess
from step.tensor_rt_post_process import TensorRTPostProcess


def build_pipeline() -> Pipeline:
    return (
        Pipeline(
            "cobble-detection",
            config=Path(__file__).with_name("config") / "stream.yml",
        )
        .step(RTSPSource("rtsp://210.99.70.120:1935/live/cctv001.stream"))
        .step(NvidiaDecode())
        .step(MetadataFromDB())
        .step(
            Async(
                TensorRTPreProcess(),
                TensorRTInference(Path(__file__).with_name("model") / "yolo11n.plan"),
                TensorRTPostProcess(),
                timeout_ms=20,
            ),
        )
        .step(BoxOverlay())
        .step(Tap(SaveInferenceResultToDB()))
        .step(NvidiaEncode())
        .step(RTSPPublish("rtsp://localhost:8554/cctv001"))
        .step(StreamReport())
    )


if __name__ == "__main__":
    pipeline = build_pipeline()
    pipeline.run()
