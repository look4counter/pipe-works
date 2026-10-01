"""예제 02: 여러 RTSP Stream을 하나의 Batch Inference로 처리한다.

이 예제는 단순히 Stream 목록을 선언하는 데서 끝나지 않는다. 로컬 실행 시
9개 카메라를 흉내 내는 GStreamer Source reader를 사용해 다음 전체 흐름을
실행한다.

    cam01 ... cam09
        -> cycle별 Frame 수집
        -> 하나의 Batch Inference
        -> stream_id 기준 결과 복원
        -> Stream별 Overlay
        -> Stream별 MediaMTX 출력 경계

실제 운영에서는 ``build_sources()``의 ``frame_reader`` 인자를 제거하면 된다.
그러면 SDK가 GStreamer appsink에서 RTSP Frame을 읽고, 나머지 Batch 수집과
결과 매핑은 이 예제 코드에 추가하지 않아도 동일하게 동작한다.
"""

from collections.abc import Callable, Iterable
from pathlib import Path

from pipeworks import DetectionBoxOverlay, Frame, Pipeline, Stream, YoloInference
from pipeworks.adapters.gstreamer import GStreamerRTSPSource
from pipeworks.adapters.outputs import MediaMTXPublisher

CONFIG_PATH = Path(__file__).with_name("config") / "multistream_batch.yaml"
MODEL_PATH = "models/cobble.engine"
CAMERA_COUNT = 9


# Python 코드에는 영상의 정체성인 Stream ID, 입력 주소, 출력 주소를 남긴다.
STREAMS = [
    Stream(
        stream_id=f"cam{index:02}",
        source=f"rtsp://cam{index:02}",
        output=f"rtsp://mediamtx/cam{index:02}",
    )
    for index in range(1, CAMERA_COUNT + 1)
]


def local_frame_reader(url: str, stream_id: str) -> Iterable[Frame]:
    """카메라 없이도 9채널 Batch를 재현하는 유한 appsink reader."""

    for sequence in range(2):
        yield Frame(
            stream_id=stream_id,
            image=f"decoded:{url}:{sequence}",
            sequence=sequence,
            metadata={"format": "RGB", "width": 1280, "height": 720},
        )


def build_sources(
    frame_reader: Callable[[str, str], Iterable[Frame]] | None = local_frame_reader,
) -> dict[str, GStreamerRTSPSource]:
    """Stream 선언을 실행 가능한 GStreamer Source 목록으로 변환한다.

    ``frame_reader``를 기본값으로 두어 예제는 외부 장비 없이 실행된다. 운영
    애플리케이션에서는 ``build_sources(None)``으로 호출해 실제 GStreamer를
    사용하거나, 테스트용 reader를 주입할 수 있다.
    """

    return {
        stream.stream_id: GStreamerRTSPSource(
            url=stream.source,
            stream_id=stream.stream_id,
            frame_reader=frame_reader,
        )
        for stream in STREAMS
    }


def build_pipeline(publisher: MediaMTXPublisher | None = None) -> Pipeline:
    """9개 입력과 하나의 Batch Inference Pipeline을 선언한다."""

    output = publisher or MediaMTXPublisher("rtsp://mediamtx/{stream_id}")
    return (
        Pipeline("cobble-9ch", config=CONFIG_PATH)
        .streams(STREAMS)
        # 이 한 줄이 cycle별 Frame 수집, Batch 생성, 결과 Demultiplex를 의미한다.
        .batch_inference(YoloInference(MODEL_PATH))
        .overlay(DetectionBoxOverlay())
        .output(output)
    )


def run_local_demo() -> None:
    """9개 fake RTSP 입력을 두 cycle 처리하고 매핑 결과를 출력한다."""

    published: list[tuple[str, str, int]] = []

    def record_publish(url: str, context, settings: dict[str, object]) -> None:
        # 실제 Publisher는 여기서 context.stream_id별 encoder/RTSP 경로로 보낸다.
        published.append((url, context.stream_id, context.frame.sequence))

    pipeline = build_pipeline(
        MediaMTXPublisher("rtsp://mediamtx/{stream_id}", publisher=record_publish)
    )
    result = pipeline.run_streams(build_sources(), max_cycles=2)

    print(pipeline.diagram())
    print("처리한 Frame:", result.metrics.frames_processed)
    print("Batch 호출 횟수:", result.metrics.batch_count)
    print("Batch에 전달한 Frame:", result.metrics.batch_items)
    print("Stream별 결과:")
    for context in result.contexts:
        print(
            f"  {context.stream_id}: sequence={context.frame.sequence}, "
            f"detections={len(context.detections)}, output={context.frame.metadata['output_url']}"
        )
    print("MediaMTX 전달 기록:", published)
    print("처리 메트릭:", result.metrics.to_json())


if __name__ == "__main__":
    run_local_demo()
