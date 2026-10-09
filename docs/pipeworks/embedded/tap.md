# Tap: 배경 후처리

`Tap`은 감싼 Step을 별도 작업자에서 실행하면서 원본 컨텍스트를 다음 단계로 전달합니다. 감싼 Step의 출력은 주 스트림에 반영하지 않습니다.

**파일 위치:** `src/pipeworks/embedded/tap.py`

```python
from pipeworks.embedded import Tap

pipeline.step(Tap(PostProcess()))
```

작업자는 동시에 하나의 입력만 처리합니다. 처리 중 들어오는 입력은 후처리에서 건너뛰며 주 스트림에는 그대로 전달합니다. 감싼 Step은 원본 컨텍스트를 읽기 전용으로 사용해야 합니다. 예외는 기록하고 원본 전달을 계속합니다. 정상적인 입력 종료 시 수락한 마지막 작업이 끝날 때까지 기다립니다.

사용자 Step은 기존 핫스왑 규칙에 따라 교체되며 내장 Step은 자동 코드 교체에서 제외됩니다. 설정은 `Tap` 섹션에서 감싼 Step에 전달합니다.

```yaml
Tap:
  offset: 10  # 감싼 Step의 설정 예시
```

이전 `Sink` 클래스와 `sink.py` 모듈은 `Tap`과 `tap.py`로 변경되었습니다. 기존 import와 `Sink:` 설정 섹션을 갱신해야 합니다.

관련 문서: [Step 구조](../models.md), [파이프라인 조립](../pipeline.md)
