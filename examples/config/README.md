# 예제 YAML 설정

이 디렉터리의 YAML은 예제에서 실제로 읽는 설정 파일이다. Python 예제의
`Pipeline(..., config=...)` 경로와 연결되어 있으므로 파일을 수정한 뒤 예제를
다시 실행하면 운영 튜닝값의 영향을 확인할 수 있다.

## 파일 목록

- `single_stream.yaml`: 단일 RTSP, YOLO, Action, RTSP 출력
- `multistream_batch.yaml`: 9개 Stream의 Batch/큐/재연결/GPU 설정
- `local_pipeline.yaml`: 카메라와 GPU 없이 실행하는 CPU 설정

## 수정 순서

1. Source 주소, 모델 경로, Action URL, Output URL은 Python 파일에서 확인한다.
2. confidence, device, timeout, retry, queue, batch 같은 동작 방식은 YAML에서 바꾼다.
3. 먼저 `local_pipeline.yaml`로 로컬 검증한다.
4. 실제 장비에서는 `configuration.md`의 운영 주의사항을 확인하고 환경별 YAML을 만든다.

지원하는 모든 섹션과 값은 저장소의 [설정 reference](../../docs/configuration.md)에
정리되어 있다.
