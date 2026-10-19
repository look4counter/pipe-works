# EveryNFrames: 프레임 간격으로 단계 묶음 실행

EveryNFrames는 모델과 무관하게 하나 이상의 Step을 순서대로 감싸고 첫 입력부터 지정 간격으로 실행합니다. 기본 interval_frames=1은 모든 입력을 처리합니다. 값이 3이면 1·4·7번째 입력을 처리하고 나머지 입력은 객체와 필드를 변경하지 않고 다음 단계로 전달합니다. 인코딩·송출을 바깥에 두면 추론을 생략한 프레임도 영상 흐름을 유지합니다.

## 사용

```python
from pipeworks.embedded import EveryNFrames, YoloInference, Backend
from step.yolo_pre_process import YoloPreProcess
from step.yolo_post_process import YoloPostProcess

pipeline.step(EveryNFrames(
    YoloPreProcess(),
    YoloInference("models/yolo11n.plan", backend=Backend.TENSORRT),
    YoloPostProcess(),
    interval_frames=3,
))

# 일반 사용자 단계도 같은 방식으로 감쌀 수 있습니다.
pipeline.step(EveryNFrames(MyProcessingStep(), interval_frames=30))
```

직접 가져오기는 `from pipeworks.embedded.every_n_frames import EveryNFrames`를 사용합니다. 일반 내부 Step은 입력 하나를 소비하고 PipelineContext 하나를 출력해야 합니다. CudaAsync가 원본 안전 판단으로 프레임을 폐기한 경우만 예외로 허용합니다. Source, 출력 없는 Sink, 여러 입력을 모으거나 출력 개수를 바꾸는 단계는 지원하지 않습니다. 입력 재소비·출력 누락·잘못된 타입·추가 출력과 일반 내부 오류는 기록하고 실패 반복자를 정리합니다. 실패 입력의 영상을 전달하고 다음 선택 입력에서 내부 반복자를 재생성합니다. 명시적인 GPU·자원 안전성 오류는 전파합니다. 마지막 입력 뒤 추가 출력은 정상 입력 종료 시 검사합니다.

## 설정과 수명

| 설정 | 기본값 | 의미 |
| --- | --- | --- |
| interval_frames | 1 | bool을 제외한 1 이상의 정수 |
| steps | 필수 | 생성자 위치 인자로 지정하는 하나 이상의 Step |

```yaml
EveryNFrames:
  interval_frames: 3
YoloInference:
  gpu_id: 0
YoloPreProcess:
  size: [640, 640]
```

YAML 값이 생성자보다 우선하고 키를 삭제하면 최초 생성자 값으로 돌아갑니다. 내부 Step의 설정은 각 클래스명 섹션을 사용합니다. 같은 클래스의 여러 래퍼에 서로 다른 간격을 지정하려면 EveryNFrames 섹션을 생략하고 생성자로 지정합니다. 카운터는 process 실행별로 독립적입니다. 실행 중 간격을 바꾸면 누적 입력 번호를 유지한 채 새 간격으로 판단합니다.

선택 프레임 사이에 내부 처리 생성기를 유지하므로 모델 세션을 재사용합니다. 정상 종료·오류·조기 종료 시 내부 생성기와 상류 반복자를 정리합니다. 사용자 Step 코드 핫스왑·실시간 YAML·중앙 프로세스 전달과 중첩 CudaAsync 설정을 지원합니다.

## 비동기 처리와 결과

```python
from pipeworks.embedded import CudaAsync

pipeline.step(EveryNFrames(
    CudaAsync(preprocess, inference, postprocess, timeout_ms=20),
    interval_frames=3,
))
```

EveryNFrames를 바깥에 두면 간격은 전체 입력 프레임 기준이며 생략 프레임은 비동기 준비도 하지 않습니다. 내부 CudaAsync가 원본을 계속 사용하는 프레임을 폐기하면 해당 프레임을 후속 내부 단계와 외부 출력에 전달하지 않고 다음 입력으로 진행합니다. 폐기된 입력도 간격 카운터에 포함되며 일반 단계의 입력 재소비·출력 누락은 경고와 원본 통과 후 반복자 재생성으로 처리합니다. 원본 사용이 끝난 timeout과 busy는 기존처럼 원본을 전달합니다. GPU 작업과 입력 참조는 기존 CudaAsync의 안전한 수명 계약을 유지합니다.

반대로 CudaAsync(EveryNFrames(...))도 사용할 수 있지만 간격은 비동기 작업자가 실제 받은 입력을 기준으로 계산하고 생략 입력에도 비동기 준비 비용이 듭니다.

래퍼는 이전 추론 결과를 재사용하거나 생략 입력의 모델 필드를 지우지 않습니다. 새 디코더 컨텍스트에서 묶음 전체를 생략하면 새 detections나 model_id가 생성되지 않습니다. YoloReport는 실제 실행한 전후처리·추론을 기록하며 이 래퍼의 생략 프레임을 추론 건너뜀 표본으로 기록하지 않습니다.

YoloInference는 받은 모든 입력을 실행합니다. 이전 inference_interval_frame 옵션은 제거되었으며 생성자와 YAML에서 오류로 거부합니다. 간격 설정은 EveryNFrames.interval_frames로 옮기세요.

## 구현 위치와 설정 검증

구현: `src/pipeworks/embedded/every_n_frames.py`. 생성자는 `EveryNFrames(*steps, interval_frames=1)`입니다. 하나 이상의 Step이 필요하고 잘못된 내부 객체는 TypeError입니다. YAML 섹션은 EveryNFrames이며 interval_frames 이외의 키도 ValueError로 거부합니다.

입출력 필드 계약은 감싼 단계에 따릅니다. 래퍼 자체가 추가하는 공개 컨텍스트 필드는 없습니다. 생략 입력은 같은 객체로 전달합니다. 선택 입력은 내부 단계가 반환한 컨텍스트를 전달하므로 내부 단계가 새 객체를 만들 수도 있습니다.
