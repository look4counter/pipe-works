# batch_collector: 호환 요청 수집

구현: src/pipeworks/batch_collector.py. 모델·GPU에 의존하지 않는 내부 배치 수집기입니다. 일반 앱은 YoloInference(batch=True)를 사용합니다.

```text
collect_batch(
    requests, deferred, max_batch_size, timeout,
    *, key, received_at,
)
```

requests는 queue.Queue, deferred는 collections.deque입니다. key(request)는 호환성을 비교할 키, received_at(request)는 time.monotonic과 같은 시계의 초 단위 도착 시각을 반환해야 합니다. timeout은 초 단위이며 모델 YAML의 밀리초는 호출자가 변환합니다. 양의 max_batch_size·유효 timeout의 검증도 호출자가 수행합니다.

먼저 deferred의 첫 요청이 있으면 사용하고 없으면 requests.get으로 첫 요청까지 제한 없이 기다립니다. 기한은 첫 요청 도착 시각+timeout이며 최대 크기에 도달하거나 요청 대기 시간이 끝날 때까지 큐를 읽습니다. 같은 키는 현재 배치에, 다른 키는 deferred 뒤에 넣습니다. 이미 deferred에 쌓인 나머지 요청을 현재 배치에 다시 합치는 탐색은 하지 않습니다.

반환은 첫 요청을 포함한 요청 목록입니다. 기한이 지났어도 비어 있지 않은 큐를 timeout=0으로 계속 읽을 수 있으므로 실행 시간의 절대 상한을 제공하지 않습니다. 결과 전달·큐 소유권·종료 신호·GPU 처리는 수행하지 않습니다. 이 동작은 [공유 추론](local_yolo_inference.md)의 내부 구성 요소입니다.
