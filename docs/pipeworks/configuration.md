# 설정 파일과 경로 규칙

## 세 종류의 설정

| 구분 | 위치 | 읽는 시점 | 용도 |
| --- | --- | --- | --- |
| 앱 설정 | Pipeline(config=Path(...)) | 생성·등록 시, 실행 중 변경 감시 | 클래스명별 Step 옵션 |
| 모델 설정 | 모델 경로의 확장자를 .yml로 바꾼 동명 파일 | 공유 작업자 최초 생성, TensorRT 개별 실행 시작 | 배치 수집 |
| 앱 코드 | 사용자 Step·실행부 생성자 | 인스턴스 생성·모델 준비 | URL·모델 경로·batch 등 |

Pipeline 설정은 UTF-8 YAML이며 최상위와 각 섹션은 매핑이어야 합니다. 빈 파일은 빈 설정으로 취급하고 RTSPSource: null이나 최상위 목록은 거부합니다. 파일이 없으면 Pipeline 생성이 실패합니다. YAML의 이름은 Python 클래스명과 정확히 같아야 합니다.

```yaml
RTSPSource:
  transport: tcp
YoloInference:
  backend: tensorrt
  gpu_id: 0
  profile_index: 0
EveryNFrames:
  interval_frames: 3
CudaAsync:
  timeout_ms: 20
```

## 우선순위와 래퍼

설정 가능한 내장 Step은 YAML → 최초 생성자 값 → 기본값 순서입니다. 삭제한 키는 직전 YAML 값이 아니라 최초 생성자 값으로 복원됩니다. 0·false·빈 목록·null은 누락이 아니며 해당 Step이 검증합니다. 같은 클래스의 인스턴스들은 같은 YAML 섹션을 사용합니다. 개별 생성자 값을 유지하려면 공통 YAML 키를 생략합니다.

CudaAsync와 EveryNFrames는 자신의 옵션만 받고 내부 Step들은 각 클래스명 최상위 섹션으로 설정합니다. TapSkipIfBusy는 TapSkipIfBusy 섹션 전체를 감싼 Step에 전달합니다. 명시적 Hotswap은 감싼 클래스명 섹션을 사용합니다. 사용자 Step의 기본값 복원은 자동으로 보장되지 않으며 _set_config_defaults와 _resolve_config를 사용해 구현합니다.

실행 중 설정은 처리 경계에서 감시하며 잘못된 변경은 이전 설정을 유지합니다. 저장 직후 실행 중인 GPU 작업까지 즉시 교체한다는 뜻은 아닙니다. URL·모델 경로·batch는 해당 생성자로 지정합니다. 인코더는 실행 도중 옵션이 바뀌어도 기존 인코더를 자동 재생성하지 않습니다.

## 모델 YAML

모델 설정은 같은 디렉터리의 동명 `.yml`을 자동으로 읽습니다. `models/model.engine`이면 `models/model.yml`을 사용합니다. `.yaml`이나 다른 이름은 탐색하지 않습니다. 파일이 없으면 기본값을 사용하며 잘못된 내용은 오류로 알립니다. 생성자에서 설정 경로를 받지 않습니다.

```python
YoloInference("models/model.engine", backend=Backend.TENSORRT)
```

```yaml
max_batch_size: 4
max_batch_wait_ms: 10
```

max_batch_size는 bool을 제외한 1 이상의 정수이며 max_batch_wait_ms는 bool을 제외한 0 이상의 유한한 밀리초입니다. 첫 요청 도착 후 추가 요청을 모으는 최대 대기 시간이며 배치가 가득 차면 즉시 실행합니다. 큐 적체나 GPU 실행을 포함한 전체 지연 상한은 아닙니다. 실행 결과 대기는 CudaAsync의 timeout_ms와 구분합니다. 이전 모델 키 batch_timeout_ms도 새 이름으로 바꿔야 합니다.

TorchScript·Ultralytics·사용자 실행부의 공유 배치는 동명 파일이 없으면 크기 1·대기 0입니다. 파일이 있으면 max_batch_size와 max_batch_wait_ms 두 키를 모두 지정해야 합니다. TensorRT는 파일이 있어도 생략한 배치 키에 각각 1과 0을 적용합니다. TensorRT의 profile_index는 모델 YAML이 아니라 YoloInference 섹션 또는 생성자로 지정합니다. 이전 timeout·timeout_ms·batch_timeout_ms 키는 오류입니다. 모델 YAML을 통한 외부 플러그인 로드는 지원하지 않습니다.

모델 YAML은 Pipeline의 실시간 설정 감시 대상이 아닙니다. 공유 작업자는 최초 설정을 캐시하므로 파일 저장만으로 배치 설정·모델을 교체하지 않습니다. 모든 클라이언트를 종료해 중앙 프로세스가 끝난 뒤 다시 실행하거나 로컬 실행 프로세스를 재시작합니다.

## 경로와 프로세스

Pipeline은 config 경로를 생성 시 resolve하지만 모든 모델·사용자 파일 경로까지 자동으로 앱 위치로 바꾸지 않습니다. 앱의 __file__ 기준 Path.resolve()로 설정·모델 경로를 만들어 넘깁니다. 같은 중앙 프로세스의 작업 디렉터리를 앱마다 바꾸지 마세요. 서로 다른 위치의 앱이 중앙 프로세스를 공유할 때 상대 모델 경로는 특히 잘못 해석될 수 있습니다.

[시작하기](getting_started.md), [Pipeline](pipeline.md), [공유 추론](local_yolo_inference.md), [TensorRT](embedded/tensor_rt_inference.md)를 참고하세요.
