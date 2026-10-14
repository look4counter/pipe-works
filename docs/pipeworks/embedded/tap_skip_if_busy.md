# TapSkipIfBusy: 배경 후처리

구현: `src/pipeworks/embedded/tap_skip_if_busy.py`. 가져오기는 `from pipeworks.embedded import TapSkipIfBusy`입니다.

## 생성자와 설정

`TapSkipIfBusy(step)`는 배경에서 실행할 Step 하나를 받습니다. 자체 설정 옵션은 없고 configure에 받은 설정 전체를 감싼 Step에 전달합니다. Pipeline에서는 TapSkipIfBusy YAML 섹션을 사용합니다. CudaAsync·EveryNFrames와 달리 내부 Step의 클래스명 섹션을 자동으로 적용하지 않습니다.

```yaml
TapSkipIfBusy:
  offset: 10  # 감싼 사용자 Step이 지원하는 설정 예시
```

## 입력과 출력

감싼 Step에 필요한 필드를 가진 컨텍스트를 입력받습니다. 같은 객체를 배경 작업자와 주 파이프라인이 공유하며 복사하지 않습니다. 주 출력은 원본 컨텍스트이고 감싼 Step의 출력은 소비 후 버립니다. 별도 결과 속성을 주 출력에 병합하지 않으며 공유 객체를 제자리 수정하면 주 파이프라인에도 영향을 줍니다. 배경 Step은 공유 입력을 읽기 전용으로 사용해야 합니다.

작업자는 동시에 하나의 입력만 처리하고 다음 입력을 요청할 때 다시 유휴 상태가 됩니다. 처리 중 들어온 새 입력은 배경 처리에서 생략하지만 주 스트림에는 그대로 전달합니다. 대기열에 입력을 계속 쌓지 않습니다.

## 오류와 종료

일반 사용자 Step은 Hotswap으로 감싸고 내장 Step과 기존 Hotswap은 그대로 사용합니다. Hotswap이 복구하지 못한 작업자 예외는 기록한 뒤 배경 작업자를 종료합니다. 이 경우 이후 입력의 배경 처리를 자동 재시작하지 않지만 주 전달은 계속합니다.

정상 입력 종료 시 수락한 작업이 끝날 때까지 기다립니다. 오류·조기 종료에서는 슬롯을 닫고 작업자 완료를 기다리지 않습니다. 별도 처리 기한은 없습니다.

```python
from pipeworks.embedded import TapSkipIfBusy

pipeline.step(TapSkipIfBusy(my_read_only_step))
```

관련 문서: [Step 계약](../models.md), [Hotswap](../hotswap.md), [전체 Step 목록](../README.md)
