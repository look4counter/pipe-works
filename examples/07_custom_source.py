"""예제 07: 사용자 정의 Source를 Pipeline에 조립한다.

Source가 어떤 라이브러리로 Frame을 읽는지는 애플리케이션의 책임이다.
SDK에 필요한 계약은 다음 두 가지뿐이다.

* 단일 실행: ``frames() -> list[Frame]``
* 연속 실행: ``stream_frames() -> Iterator[Frame]``

실제 프로젝트에서는 ``read_frame()`` 위치에 OpenCV, 산업용 카메라 SDK,
WebSocket, 공유 메모리 또는 자체 수신기를 연결한다. 이후 추론 호출,
stream_id 보존, 결과 처리, output 전달은 SDK Runtime이 담당한다.
"""

from dataclasses import dataclass

from pipeworks import DetectionBoxOverlay, Frame, Pipeline, RTSPPublisher, Stream, YoloInference


@dataclass
class CustomFiniteSource:
    """파일/DB/테스트 데이터처럼 유한한 Frame 목록을 제공하는 Source."""

    stream_id: str
    frame_count: int = 2
    name: str = "CustomFiniteSource"

    def frames(self) -> list[Frame]:
        return [
            Frame(
                stream_id=self.stream_id,
                image=f"custom-frame-{sequence}",
                sequence=sequence,
            )
            for sequence in range(self.frame_count)
        ]


@dataclass
class CustomLiveSource:
    """외부 수신기를 감싼 연속 Source."""

    stream_id: str
    frame_count: int = 2
    name: str = "CustomLiveSource"

    def stream_frames(self):
        for sequence in range(self.frame_count):
            # 실제 구현에서는 여기서 blocking/non-blocking 수신기를 호출한다.
            yield Frame(
                stream_id=self.stream_id,
                image=f"live-frame-{sequence}",
                sequence=sequence,
            )


def run_finite_source() -> None:
    """frames() 계약을 사용하는 단일 Pipeline."""

    pipeline = (
        Pipeline("custom-finite-source")
        .source(CustomFiniteSource("custom-file"))
        .inference(YoloInference("models/cobble.engine"))
        .overlay(DetectionBoxOverlay())
        .output(RTSPPublisher("memory://custom-output"))
    )
    result = pipeline.run()
    print("유한 Source 결과:", [(context.stream_id, context.frame.sequence) for context in result.contexts])


def run_live_source() -> None:
    """stream_frames() 계약을 사용하는 연속 Pipeline."""

    pipeline = (
        Pipeline("custom-live-source")
        .streams([Stream("custom-live", source="custom://live")])
        .inference(YoloInference("models/cobble.engine"))
        .output(RTSPPublisher("memory://custom-live-output"))
    )
    result = pipeline.run_streams(
        {"custom-live": CustomLiveSource("custom-live")},
        max_cycles=2,
    )
    print("연속 Source 결과:", [(context.stream_id, context.frame.sequence) for context in result.contexts])
    print("처리 메트릭:", result.metrics.to_json())


if __name__ == "__main__":
    run_finite_source()
    run_live_source()
