# 공개 계약

```python
from pipeworks.embedded import Async
wrapped = Async(step, timeout_ms=5)
```

`step`은 `Step` 인스턴스이다. `timeout_ms`는 불리언을 제외한 유한한 0 이상의 숫자이다. 성공 결과는 원본 속성 사전을 교체하되 원본 객체 식별은 유지한다. 실패·시간 초과·사용 중 통과는 원본을 바꾸지 않는다.

```yaml
Async:
  timeout_ms: 10
  step:
    inference_interval: 3
```

`step` 매핑이 없으면 `timeout_ms` 외 구성 항목을 감싼 단계에 전달한다. 감싼 단계 이름의 최상위 구성은 자동 조회하지 않는다.

감싼 단계는 입력마다 한 번 출력하고 작업을 출력 전에 마쳐야 한다. 출력 후 데이터를 수정하거나 읽기 전용 공유 스트림을 수정해서는 안 된다. 외부 저장·전송은 취소하지 않는다. 소스·집계·다중 출력은 지원하지 않는다.
