# 빠른 검증

## 준비와 검증

프로젝트 가상환경을 사용한다. 실제 추론은 CUDA와 YOLO 감지 모델 파일이 필요하다.

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -p test_yolo_inference.py
.venv/Scripts/python.exe -m unittest discover -s tests
```

설정·건너뜀·원시 출력·오류·배치 분리가 통과해야 한다. CUDA가 없으면 GPU 검증은 명시적으로 건너뛴다.

## 연결

examples를 모듈 탐색 경로에 추가하고 COCO YOLO11 가중치를 준비한다.

```python
from pipeworks.embedded import CudaAsync, YoloInference, YoloDetectReport
from step.yolo_pre_process import YoloPreProcess
from step.yolo_post_process import YoloPostProcess

pipeline.step(CudaAsync(
    YoloPreProcess(),
    YoloInference('models/yolo11n.pt', backend='ultralytics', id='vehicle'),
    YoloPostProcess(),
    timeout_ms=100,
))
pipeline.step(YoloDetectReport())
```

예제 후처리는 기본 COCO 이름을 사용하며 FP32/FP16 감지 예측을 처리한다. 사용자 모델은 names를 지정하고 이미 NMS를 포함한 모델은 end2end=True로 설정한다. 추론만 연결하면 model_output의 output0에서 원시 예측을 확인한다. 전체 연결은 전처리·추론·후처리가 YOLO 보고 완료 표본 하나에 기록되어야 한다.

## 실행 결과: 2026-10-12

### 공통 계약 검증

- 관련 테스트 최종 237개가 통과했다. 공통 계약·YOLO 처리/추론·TensorRT 전처리/후처리/추론·양쪽 로컬 배치·모델 ID·비동기·보고·프레임 수명·기본 설정을 포함한다.
- 공통 계약 테스트 9개에서 두 전처리와 두 후처리의 모든 교차 조합, 이름 있는 YOLO 단일 입력, FP16·사용자 이름, 이전 좌표/프로파일 입력 및 정리를 검증했다.
- 실제 YOLO 모델과 기존 TensorRT 엔진을 각 전후처리 조합으로 개별·공유 배치 실행했다. 보고 하나만 활성화한 경우와 양쪽을 활성화한 경우 모두 실제 백엔드의 전처리·추론·후처리·전체 시간이 완료 표본 하나로 기록됐다.
- 혼합 계열의 CudaAsync timeout/busy/partial이 실제 추론 백엔드에만 기록되는 것을 확인했다.
- 기존 GPU/NMS 최적화 검증을 유지했다. 후보 6개는 raw 형식을 명시적으로 처리하며 참조 테스트에서 라이브러리 자동 end2end 분기를 우회한다. 원본 프레임 비교 테스트는 생산 스트림 완료를 기다린 뒤 복제하여 이전의 비교 경합을 제거했다.
- 문서의 공통 필드는 model_input/model_output/model_id/image_transform/detections이며 두 후처리 기본 classes는 None이다. 차량만 필요하면 classes=[2]를 명시한다.
- 초기 회귀의 프로파일 정리 누락과 기본값 기대값 갱신 누락을 수정한 뒤 최종 확장 회귀가 모두 통과했다. 공백 검증과 공통 모듈 구문 컴파일도 통과했다.

공통 계약만 별도로 확인하려면 다음을 실행한다.

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -p test_inference_contract.py
```

실제 모델의 자료형·형상·입출력 이름은 모델 규칙을 따른다. 전체 저장소의 이전 미관련 실패를 수정한 것은 아니며 이번 요청의 관련 회귀 범위를 검증했다.

### 추가 요청의 전후처리 검증

- Step 직접 상속 변경 후 YOLO 처리·추론 테스트 총 44개가 통과했다. TensorRT 전처리 모듈을 차단한 가져오기·생성 검증과 실제 CUDA 모델의 개별·공유 배치 처리 및 전체 YOLO 보고를 확인했다.

- tests/test_yolo_processing.py의 신규 테스트 19개와 기존 추론 테스트 24개가 모두 통과했다. CUDA 검증을 건너뛰지 않았다.
- 로컬 설정에서 만든 실제 YOLO11 감지 모델로 개별·공유 배치의 전처리 → 추론 → 후처리를 실행했다. 모델 다운로드 없이 원본 프레임 보존·결과 형상·임시 정보 정리·전처리/추론/후처리/전체 시간의 완료 표본 1개를 확인했다.
- 신규·기존 추론·비동기·보고·프레임 해제·TensorRT 전후처리·YOLO 모델 ID/배치/설정 모듈을 함께 실행하여 관련 테스트 총 169개가 통과했다.
- 첫 관련 회귀에서 기존 TensorRT 전처리의 프레임 비교가 한 번 실패했으나 해당 모듈 13개 단독 재실행 및 최종 169개 통합 실행에서 통과했다. 기존 테스트나 TensorRT 예제는 수정하지 않았다.
- 단일 스트림 예제의 build_pipeline 호출과 새 클래스 가져오기를 검증했다. 실제 RTSP 서버 접속은 수행하지 않았다.
- git diff --check 및 새 소스·테스트 파일의 공백 검증이 통과했다.

### 최초 추론 단계 검증 기록

- 신규 계약 테스트 최종 24개 통과. CUDA 검증을 건너뛰지 않았으며 로컬 설정으로 생성한 실제 YOLO11 모델의 개별 추론과 기존 전후처리 연결도 통과했다. 모델 다운로드는 하지 않았다.
- 공유 배치의 요청별 출력 소유권, 오류 전달, 오류 후 모델 재로딩, YAML 적용, 비동기 완료·타임아웃·바쁨 보고를 검증했다.
- 전체 테스트 최초 실행: 393개 중 389개 통과, 실패 1개와 오류 3개. 이 실행의 신규 테스트는 21개였고 이후 추가한 검증은 최종 신규 테스트 실행에서 모두 통과했다.
- 중앙 프로세스의 Windows 임시 폴더 정리 오류는 해당 테스트 단독 재실행에서 통과했다.
- 남은 기존 실패는 YoloDetect의 별도 스트림 기대값 불일치 1개와 다중 스트림 예제의 누락된 step.post_process 모듈 오류 2개다. 변경 전 HEAD의 공개 내보내기와 CudaAsync 코드를 별도 검증 프로세스 메모리에 로드하여 동일한 세 실패가 재현됨을 확인했다. 기존 YoloDetect와 예제 소스는 수정하지 않았다.
- git diff --check에서 공백 오류가 없다. 전체 테스트가 모두 통과했다고 주장하지 않으며 이번 기능에서 새 회귀 실패는 발견하지 않았다.

## GPU 전용 실행 검증

프로젝트 가상환경과 CUDA가 필요하다. 라이브러리 독립 GPU 실행과 CPU 전환 거부를 다음 명령으로 확인한다.

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -p test_yolo_gpu_backends.py
.venv/Scripts/python.exe -m unittest discover -s tests -p test_yolo_inference.py
```

두 이름 있는 GPU 입력과 중첩 출력을 실행하고 모든 텐서가 지정 GPU에 남아야 한다. CPU 전환 모델은 오류로 거부되고 공유 배치 결과는 서로 다른 저장소를 가져야 한다. 기존 .pt 예제는 stream.yml의 backend: ultralytics를 명시한 후 실행한다.

## GPU 전용 범용화 검증 결과: 2026-10-13

- 관련 테스트 69개 통과: GPU 실행부 15개, YOLO 추론 25개, 공통 계약 9개, YOLO 전후처리 20개. 실제 CUDA 테스트를 건너뛰지 않았다.
- Ultralytics를 차단하고 TorchScript 다중 입력·다중 출력, 정수 입력·비이미지 형상, 사용자 실행부 가져오기, 모든 중첩 출력 보존, 버퍼 소유권과 공유 배치 실행을 확인했다.
- 모델 내부 CPU 이동 후 GPU 복귀, CPU 텐서 생성, 입력 데이터 scalar 읽기, 출력 이름 충돌, 공유 배치 축 오류를 거부한다. 공유 오류는 모든 요청에 전달된다.
- 현재 examples/model/yolo11n.pt를 640×640 GPU 입력으로 실행했다. 같은 세션에서 FP32 → FP16 → FP32 전환이 통과했고 매번 (1,84,8400) 주 예측과 총 6개 원시 출력을 모두 GPU에 유지했다. 정적 stride 메타데이터가 정밀도 전환 때 감시와 충돌한 문제는 수정하고 회귀 테스트를 추가했다.
- 전체 회귀는 새 정밀도 테스트 추가 전 440개 중 436개가 통과했고 기존 오류 3개·실패 1개가 남았다. 이후 변경 영향 범위의 테스트를 다시 검증했다.
- 남은 기존 문제: test_box_overlay의 이전 예제 단계 검색 기대, test_multiple_stream_example의 누락된 step.post_process 가져오기 2건, test_yolo_detect의 별도 CUDA 스트림 기대 1건. 변경하지 않은 예제·감지 코드의 기존 검사이며 각각 단독 실행에서도 같은 문제가 재현된다. 이번 범위에서 수정하지 않았다.
- 새 실행부·추론·공유 실행 코드와 신규 GPU/추론 테스트는 Ruff 검사 및 포맷 확인을 통과했다. 기존 공통 계약 테스트의 dict 문법·반복 변수 캡처 스타일 진단은 기존 동작으로 유지했다.
- CPU는 파일 로딩·제어·정적 모델 메타데이터에 사용한다. 입력과 원시 출력 및 PyTorch 모델 연산은 지정 GPU에서 실행하며 자동 CPU 실행을 제공하지 않는다. 외부 네이티브 실행부의 내부는 사용자 구현이 GPU 계약을 지켜야 한다.
- stream.yml의 YoloInference에는 기존 체크포인트의 backend: ultralytics를 명시했고 profile_index는 제거했다. 감지 클래스 필터와 영상 송수신 설정은 보존했다. 실제 RTSP 송수신은 이 검증 범위에 포함하지 않았다.

## Backend 필수 선택

Backend.TORCHSCRIPT와 Backend.ULTRALYTICS를 공개한다. YoloInference의 backend는 필수 키워드이며 사용자 정의 모듈:클래스 문자열과 YAML 문자열을 유지한다. YAML 내장 값은 enum으로 정규화하고 설정 제거 시 생성자 선택으로 복원한다. 공개 가져오기·생략 오류·설정 복원과 기존 추론 회귀로 검증한다.


## Backend 검증 결과: 2026-10-13

- tests/test_yolo_inference.py: 27개 통과. 공개 enum, 필수 인자 오류, YAML 선택 정규화·복원 및 실제 GPU 모델 실행 포함.
- tests/test_yolo_gpu_backends.py: 15개 통과. TorchScript 및 사용자 정의 실행부·공유 실행 검증 포함.
- tests/test_yolo_processing.py: 20개 통과.
- tests/test_inference_contract.py: 9개 통과. 실제 YOLO·TensorRT 교차 계약 및 비동기 검증 포함.
- 총 71개 통과. git diff --check 통과.


## TensorRT 통합 검증: 2026-10-13

새 통합 API와 기존 호환성을 포함한 12개 관련 테스트 모듈 198개가 통과했다. 실제 GPU TensorRT 개별·공유 엔진, 공통 backend 로더, 동적 프로파일과 플러그인, 출력 소유권, YOLO/TensorRT 전후처리 교차 계약, CudaAsync와 보고, 생성자/YAML 복원 및 예제 Overlay 순서를 검증했다. git diff --check도 통과했다.

추가 범위의 test_yolo_detect.py 회귀는 단독 실행 23개 중 GPU 좌표·별도 스트림 검증 1개가 실패했다. 이 테스트와 YoloDetect 실행 코드는 이번 작업에서 변경하지 않았으며 해당 실패는 통합 관련 198개 검증과 구분하여 기록한다.

## TensorRTInference 제거 검증: 2026-10-13

관련 12개 모듈 198개 테스트가 통과했다. 이전 클래스의 공개 export와 모듈 부재를 검증하고 통합 API로 실제 GPU TensorRT 개별·공유 실행, 엔진 프로파일·플러그인·입출력, 식별자, YAML 덮어쓰기·복원, 비동기 및 전체 보고와 예제 순서를 확인했다.

실행 코드·예제·현재 문서의 이전 클래스 참조는 0개이며 삭제 부재를 확인하는 테스트에만 이전 이름을 남겼다. Step 레퍼런스 JavaScript 구문, 6개 페이지 연결, YoloInference backend 필수 설정 표와 출력 연결을 검증했다. TensorRT Python 문서 예제 8개의 구문 검증과 git diff --check도 통과했다. TensorRTReport는 유지했다.

## 공통 보고 통합 검증: 2026-10-13

관련 12개 모듈 201개 테스트가 통과했다. Report 클래스·모듈·별도 통계 저장소의 삭제를 확인하고, 하나의 Report가 YOLO·ULTRALYTICS·TORCHSCRIPT·TensorRT·사용자 실행부를 활성화하여 분리 출력하며 종료 시 비활성화하는 계약을 검증했다. 실제 GPU TensorRT 개별·공유 파이프라인도 공통 Report로 연결하여 전체 표본을 확인했다.

프로파일 중첩과 원래 컨텍스트 복원, 전후처리의 실제 backend 연결 및 중복 완료 방지, 공유 배치의 실행 범위 격리, 비활성 이벤트 생성 방지, busy·timeout·partial과 기존 GPU·설정·Overlay 회귀를 확인했다. 배치 워커의 임시 프로파일 분류 정리 후 추론·전후처리 테스트 47개도 다시 통과했다.

실행 코드·예제·현재 문서에 이전 클래스·모듈 의존성이 남지 않았으며 삭제 검증에만 이전 이름을 남겼다. 보고 Python 문서 예제 4개 구문 검증과 git diff --check가 통과했다.

## YoloReport 명칭 변경 검증: 2026-10-13

관련 12개 모듈 201개 테스트가 통과했다. YoloReport의 공개 export와 pipeworks.embedded.yolo_report에서 가져오는 클래스가 동일함을 확인했고 이전 클래스·모듈 별칭이 없음을 검증했다. 실행 코드·테스트·예제·현재 문서의 이전 이름 참조는 0개다.

기존 혼합 backend 출력·활성화·종료 정리, 실제 GPU 개별·공유 추론, 전후처리·배치·비동기·프로파일·설정·Overlay 계약을 유지했다. YoloReport 문서 Python 예제 4개 구문 검증과 git diff --check도 통과했다.

## 세 backend 중앙 배치 검증 결과: 2026-10-13

세 backend의 실제 중앙 프로세스 통합 테스트 3개가 모두 실행되어 통과했다. GPU 생략은 0개이며 기존 배치·보고·GPU 계약 회귀 82개도 통과했다. 운영 Batch 구현을 수정하지 않고 검증 코드와 산출물만 추가했다.

| 실행부 | 실제 중앙 PID | 실제 배치 크기 | 세션 재사용 | GPU 요청별 결과 | 보고 완료 |
| --- | --- | --- | --- | --- | --- |
| Ultralytics | 18704 | 2, 2 | 같은 세션 2회 | 요청 4개 모두 개별 참조와 일치 | 파이프라인별 2개 |
| TorchScript | 16984 | 2, 2 | 같은 세션 2회 | 요청 4개 모두 개별 참조와 일치 | 파이프라인별 2개 |
| TensorRT | 13640 | 2, 2 | 같은 세션 2회 | 요청 4개 모두 개별 참조와 일치 | 파이프라인별 2개 |

각 실행부는 테스트 전용 중앙 그룹에서 두 Pipeline.run 호출을 실제 AF_PIPE로 전달했다. Source·배치 워커·Sink의 PID가 중앙 서버 ping 응답 PID와 같고 호출 프로세스와 다름을 확인했다. 실제 모델 forward를 관찰했으며 모의 모델·모의 IPC로 대체하지 않았다.

입력은 중앙 프로세스의 GPU에서 생성했고 모든 출력은 동일 GPU의 배치 1 텐서였다. 모든 출력 이름·값을 개별 추론과 비교하고 요청별 출력을 변경하여 다른 요청의 결과가 유지됨을 확인했다. CudaAsync와 YoloReport에서 실행·큐 대기·입력 결합·출력 복사·전체 표본도 요청별로 확인했다.

검증 모델은 로컬 생성 YOLO11 가중치, CPU 스칼라 읽기가 없는 GPU 연산 TorchScript 모델, 배치 1~4 동적 프로파일을 가진 실제 TensorRT 엔진이다. 입력은 FP32 1×3×32×32이고 모델별 max_batch_size=2, timeout_ms=5000 설정을 사용했다. 사용자별 학습 모델의 정확도나 성능 측정이 아니라 세 실제 실행부의 중앙 전달·공유 배치 계약 검증이다.

테스트 전용 서버·모델·진단 파일을 정리했고 git diff --check가 통과했다.

## 공유 모듈 통합 검증 방법

통합 후 test_local_yolo, test_local_tensor_rt의 이관 테스트와 test_yolo_inference, test_yolo_gpu_backends, test_detection_report 및 TensorRT 단계 회귀를 실행한다. test_central_yolo_inference에서 세 backend가 실제 중앙 프로세스의 통일된 워커 스레드에서 두 라운드 배치 2, 세션 재사용, 독립 GPU 결과 및 완료 보고를 제공해야 한다. 이전 두 모듈의 소스와 현행 실행 가져오기는 남지 않아야 한다.

## 공유 모듈 통합 검증 결과: 2026-10-13

local_yolo_inference.py의 단일 _ModelWorker로 수집·캐시·CUDA 대기·결과 분리·보고·실패 세션 정리를 통합했다. local_yolo.py와 local_tensor_rt.py는 제거했다. YoloInference의 원시 GPU 출력과 YoloDetect의 GPU Results 계약, TensorRT plugins·profile_index 설정과 세션 격리 및 복구를 유지했다.

통합 부재·옵션 검증을 포함한 관련 13개 회귀 모듈에서 178개 테스트가 모두 통과했다(27.169초, 생략 없음). 실제 pt/engine 감지, profile별 재사용·실패 복구, 입력 CUDA 이벤트 대기, 독립 출력 및 보고를 확인했다. 기존 개별 감지의 별도 스트림 단정은 생산 코드의 기존 호출자 스트림 계약에 맞게 수정했다.

세 backend 실제 중앙 배치 3개도 모두 통과했다(21.390초, 생략 없음). 전체 181개가 통과했다.

| backend | 중앙 PID | 실제 배치 크기 | 세션 재사용 | GPU 출력 요청 | 완료 보고 |
| --- | --- | --- | --- | --- | --- |
| TENSORRT | 7784 | 2, 2 | 같은 세션 | 4 | 파이프라인별 2 |
| TORCHSCRIPT | 7696 | 2, 2 | 같은 세션 | 4 | 파이프라인별 2 |
| ULTRALYTICS | 35204 | 2, 2 | 같은 세션 | 4 | 파이프라인별 2 |

현행 소스·문서에 이전 모듈 의존성은 없으며 제거 확인 테스트만 이전 이름을 사용한다. 감지 직접 호출은 infer_detection으로 이관했다. 테스트가 만든 중앙 서버와 임시 파일은 정리되었다.

## 전후처리 이동 검증 방법

새 삭제·코어 독립성 테스트와 test_image_transform, test_tensor_rt_preprocess, test_yolo_processing, test_tensor_rt_processing, test_tensor_rt_postprocess_optimized, test_inference_contract를 실행한다. 보고·프레임 해제·비동기·설정·Overlay의 새 조합과 실제 pt/engine 원시 추론 및 세 backend 중앙 배치를 검증한다. 네 코어 이미지 모듈과 YoloDetect를 가져올 수 없어야 하며 코어에서 step 예제 의존성이 없어야 한다.

## 전후처리 예제 이동 및 YoloDetect 삭제 결과: 2026-10-13

examples/step/yolo_pre_process.py가 NV12 변환·ImageTransform·설정·프레임 읽기·리사이즈·정규화·GPU 입력 생성을 직접 구현한다. yolo_post_process.py가 감지 설정·출력 검증·필터/NMS·좌표 복원·감지 저장·보고 및 정리를 직접 구현한다. TensorRT 전후처리 예제는 Step 직접 상속과 기존 이름/옵션을 유지하면서 YOLO 예제의 메서드를 재사용한다.

코어의 image.py·image_transform.py·image_preprocessing.py·detection_postprocessing.py와 embedded/yolo_detect.py 및 공개 YoloDetect를 삭제했다. 공유 워커의 감지 요청·predictor·감지 세션·infer_detection도 제거했다. 코어는 예제 모듈과 Ultralytics를 차단한 새 프로세스에서도 가져올 수 있다. 이전 경로의 호환 모듈은 남기지 않았다.

관련 20개 회귀 모듈에서 242개 테스트가 통과했다(46.523초, 생략 없음). 좌표·불변 정보·FP16/FP32·NV12/RGB/BGR·설정·필터/NMS·실제 모델·프레임 해제·비동기·보고·Overlay·다중 스트림·원시 추론·profile 격리/복구를 확인했다. 삭제된 감지 전용 테스트는 제거하고 공통 검증은 새 단계 조합으로 이관했다.

실제 중앙 검증 4개도 통과했다(23.655초, 생략 없음). 세 backend의 두 파이프라인·두 라운드는 모두 배치 2, 세션 재사용, 독립 GPU 출력 4개 및 파이프라인별 완료 보고 2개를 유지했다. 중앙 GPU 감지 검증은 예제 전처리·YoloInference·예제 후처리를 실제 TensorRT 엔진과 연결해 GPU 결과의 원본 크기 (64,64)를 확인했다. 전용 테스트 서버만 종료하고 소유한 자원을 정리했다. 전체 246개가 통과했다.

| backend | 중앙 PID | 실제 배치 | 세션 재사용 | GPU 출력 | 완료 보고 |
| --- | --- | --- | --- | --- | --- |
| TENSORRT | 30480 | 2, 2 | 같은 세션 | 요청 4개 | 파이프라인별 2 |
| TORCHSCRIPT | 40948 | 2, 2 | 같은 세션 | 요청 4개 | 파이프라인별 2 |
| ULTRALYTICS | 30276 | 2, 2 | 같은 세션 | 요청 4개 | 파이프라인별 2 |

현행 문서의 추론 코드 예제 32개와 레퍼런스 JavaScript 구문 검증도 통과했다. 삭제 경로는 현행 소스·예제·문서에 남지 않는다. 다중 스트림 예제의 기존 누락 PostProcess 가져오기는 현재 SaveInferenceResultToDB로 연결했다. 이전 유지 요구는 사용자의 이번 삭제 지시로 대체한다.
