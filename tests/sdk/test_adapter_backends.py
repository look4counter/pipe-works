from pipeworks import Detection, DetectionResult, Frame, PipelineContext
from pipeworks.adapters.actions import MQAdapterAction
from pipeworks.adapters.gstreamer import GStreamerRTSPSource
from pipeworks.adapters.inference import TensorRTInference, UltralyticsYoloInference
from pipeworks.adapters.outputs import MediaMTXPublisher


def test_gstreamer_source_uses_injected_frame_reader() -> None:
    source = GStreamerRTSPSource(
        "rtsp://camera/main",
        stream_id="cam01",
        frame_reader=lambda url, stream_id: [Frame(stream_id, image=url)],
    )

    assert source.frames()[0].stream_id == "cam01"


def test_inference_adapters_accept_runtime_backends() -> None:
    context = PipelineContext(Frame("cam01"))

    def result(stage: str) -> DetectionResult:
        return DetectionResult("cam01", stage, [Detection((0, 0, 1, 1), 0.9, 1)], 0)

    yolo = UltralyticsYoloInference("model.pt", predictor=lambda image, settings: [result("yolo")])
    tensorrt = TensorRTInference("model.engine", runner=lambda image, settings: result("trt"))

    assert yolo.infer(context, {}).stage == "yolo"
    assert tensorrt.infer(context, {}).stage == "trt"


def test_mq_and_mediamtx_adapters_forward_to_backends() -> None:
    context = PipelineContext(Frame("cam01"))
    published: list[tuple[str, dict[str, object]]] = []
    written: list[str] = []
    action = MQAdapterAction("events", publisher=lambda topic, message: published.append((topic, message)))
    output = MediaMTXPublisher("rtsp://out", publisher=lambda url, item, settings: written.append(url))

    action.execute(context, {})
    output.write(context, {})

    assert published[0][0] == "events"
    assert written == ["rtsp://out"]
