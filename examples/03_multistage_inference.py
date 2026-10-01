"""예제 03: 1차 추론 결과를 2차 추론으로 연결한다.

일반적인 흐름은 전체 Frame에서 객체를 찾은 뒤, DetectionCrop 같은 Transform으로
관심 영역을 만들고, 2차 모델로 세부 분류를 수행하는 것이다. 각 stage의 결과는
Context에 이름을 가지고 보존된다.
"""

from pipeworks import (
    DetectionBoxOverlay,
    DetectionCrop,
    Pipeline,
    RTSPPublisher,
    RTSPSource,
    YoloInference,
)

pipeline = (
    Pipeline("cobble-multistage")
    .source(RTSPSource("rtsp://camera/main"))
    # stage 이름을 지정하면 primary/secondary 결과를 구분해서 조회할 수 있다.
    .inference(YoloInference("models/primary.engine", stage="primary"))
    # Transform은 이전 stage의 detections를 읽고 다음 stage 입력을 준비한다.
    .transform(DetectionCrop())
    .inference(YoloInference("models/secondary.engine", stage="secondary"))
    .overlay(DetectionBoxOverlay())
    .output(RTSPPublisher("rtsp://mediamtx/result"))
)


if __name__ == "__main__":
    result = pipeline.run()
    print("보존된 추론 stage:", list(result.contexts[0].results))
