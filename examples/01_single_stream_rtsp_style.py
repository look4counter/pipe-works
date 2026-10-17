import logging
from pathlib import Path
from pipeworks import Backend
from pipeworks import Pipeline
from pipeworks.embedded import (
    RTSPSource,
    RTSPPublish,
    NvidiaEncode,
    NvidiaDecode,
    StreamReport,
    CudaAsync,
    EveryNFrames,
    YoloReport,
    YoloInference,
)
from step.tensor_rt_pre_process import TensorRTPreProcess
from step.tensor_rt_post_process import TensorRTPostProcess
from step.box_overlay import BoxOverlay


def build_pipeline() -> Pipeline:
    return (
        Pipeline(
            "cobble-detection",
            config=Path(__file__).with_name("config") / "stream.yml",
            batch_process="development",
        )
        .step(RTSPSource("rtsp://210.99.70.120:1935/live/cctv001.stream"))
        .step(NvidiaDecode())
        .step(
            EveryNFrames(
                CudaAsync(
                    TensorRTPreProcess(),
                    YoloInference(
                        Path(__file__).with_name("model") / "yolo11n.plan",
                        backend=Backend.TENSORRT,
                        batch=False,
                    ),
                    TensorRTPostProcess(),
                    timeout_ms=20,
                ),
            ),
        )
        .step(YoloReport())
        .step(BoxOverlay())
        .step(NvidiaEncode())
        .step(RTSPPublish("rtsp://localhost:8554/cctv001"))
        .step(StreamReport())
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    pipeline = build_pipeline()
    pipeline.run()
