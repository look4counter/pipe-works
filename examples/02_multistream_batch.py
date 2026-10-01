"""예제 02: 여러 RTSP Stream을 하나의 Batch Inference로 처리한다.

개발자는 Batch 생성과 결과 Demultiplex를 직접 작성하지 않는다. SDK가 각
Frame의 stream_id를 보존하고, 추론 결과를 원래 Stream으로 되돌린다.
"""

from pipeworks import DetectionBoxOverlay, Pipeline, Stream, YoloInference

# 실제 운영에서는 이 목록을 YAML이나 배포 환경에서 생성해도 된다.
streams = [
    Stream(
        f"cam{index:02}",
        source=f"rtsp://cam{index:02}",
        output=f"rtsp://out/cam{index:02}",
    )
    for index in range(1, 10)
]

pipeline = (
    Pipeline("cobble-9ch")
    .streams(streams)
    # 이 한 줄이 9개 Frame의 수집, Batch 생성, 결과 매핑을 의미한다.
    .batch_inference(YoloInference("models/cobble.engine"))
    .overlay(DetectionBoxOverlay())
)


if __name__ == "__main__":
    result = pipeline.run()
    print("처리한 Stream:", [context.stream_id for context in result.contexts])
    print("Batch 크기:", result.metrics.batch_size)
    print("처리 메트릭:", result.metrics.to_json())
