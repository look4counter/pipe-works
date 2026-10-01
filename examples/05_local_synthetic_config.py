"""예제 05: 외부 YAML로 운영 튜닝값을 바꾸는 로컬 실행 예제.

모델 경로와 Pipeline 순서는 Python에 남기고, confidence/device/queue 같은
동작 방식만 YAML에서 조정한다. 카메라와 GPU 없이도 설정 병합을 검증할 수 있다.
"""

from pathlib import Path

from pipeworks import DetectionBoxOverlay, Pipeline, SyntheticSource, YoloInference

# 배포 시에는 이 파일 대신 환경별 설정 경로를 전달할 수 있다.
config_path = Path(__file__).with_name("local_pipeline.yaml")

pipeline = (
    Pipeline("local-configured-pipeline", config=config_path)
    .source(SyntheticSource("local-cam", frame_count=3, width=320, height=180))
    # Source와 Model의 정체성은 Python 코드에서 읽힌다.
    .inference(YoloInference("models/local.engine"))
    .overlay(DetectionBoxOverlay())
)


if __name__ == "__main__":
    result = pipeline.run()
    print("적용된 메트릭:", result.metrics.to_json())
    print("Detection confidence:", [context.detections[0].confidence for context in result.contexts])
