"""예제 01: 한 대의 카메라를 처리하는 가장 기본적인 Pipeline.

이 파일의 체인은 영상 처리 프로그램의 실행 흐름을 그대로 읽어주는
Architecture Diagram 역할을 한다. 로컬에서는 RTSP 주소를 설명자로만
사용하므로 카메라가 없어도 DSL과 검증 흐름을 확인할 수 있다.
"""

from pathlib import Path

from pipeworks import (
    DetectionBoxOverlay,
    MQPublishAction,
    Pipeline,
    RTSPPublisher,
    RTSPSource,
    StaticBoxOverlay,
    SvgSendAction,
    YoloInference,
)

pipeline = (
    Pipeline("cobble-detection", config=Path(__file__).with_name("config") / "single_stream.yaml")
    # 무엇을 입력으로 받을지 코드에서 바로 읽을 수 있다.
    .source(RTSPSource("rtsp://camera/main"))
    # 모델 경로는 What이므로 Python 인자로 둔다.
    .inference(YoloInference("models/cobble.engine"))
    # 여러 Overlay는 선언한 순서대로 적용된다.
    .overlay(StaticBoxOverlay())
    .overlay(DetectionBoxOverlay())
    # Action은 영상 출력과 분리된 비동기 부수 효과다.
    .action(SvgSendAction("http://server/api/svg"))
    .action(MQPublishAction("cobble.detected"))
    # 최종 영상이 어디로 나가는지도 코드에 남는다.
    .output(RTSPPublisher("rtsp://mediamtx/cobble"))
)


if __name__ == "__main__":
    # diagram()을 먼저 출력하면 코드를 실행하지 않아도 흐름을 확인할 수 있다.
    print(pipeline.diagram())
    result = pipeline.run()
    print("처리 메트릭:", result.metrics.to_json())
