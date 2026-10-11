# 검증과 사용

## YOLO 모델 ID 검증 (2026-10-11)

`YoloDetect(model_path, id="vehicle")`도 공통 `detections[id]` 사전에 저장한다. 생성자 id를 생략하면 확장자 포함 파일명이다. 여러 인스턴스의 ID를 다르게 쓰면 YAML 공통 id는 생략한다. 결과 누락은 현재 키의 None이며 다른 키는 유지한다. 두 모델의 추론을 끝낸 뒤 Overlay를 실행한다.

새 ID 검증 10개·기존 YOLO 23개·배치 15개·local_yolo 10개·보고 14개·Overlay 5개·TensorRT ID 13개·생성자 구성 11개·Async 38개·프레임 해제 6개를 실행했다. 총 145개 중 143개 통과하고 실제 .engine 파일이 필요한 기존 검증 2개는 건너뛰었다. 실제 같은 .pt 모델의 직렬 결과 보존·TensorRT와 혼합 저장·입력 경계 ID 고정·개별/배치 오류 정책·늦은 비동기 결과의 원본 사전 격리를 확인했다. local_yolo의 직접 반환 계약은 유지했다.

`git diff --check`가 통과했다. 수렴 점검에서 FR-022~024·SC-011과 구성·공통 결과 계약·문서·기존 오류 정책 사이에 남은 구현 차이는 없으며 추가 작업은 없다.

## 모델 ID별 결과 검증 (2026-10-11)

TensorRTInference의 id를 생략하면 확장자 포함 파일명을 사용한다. 같은 모델을 여러 번 사용하면 생성자에 서로 다른 id를 지정하고 YAML의 공통 id는 생략한다. 결과는 detections[id]에서 읽고 Overlay는 모든 추론 뒤에 배치한다. 비동기 직렬 모델은 모델별 별도 CudaAsync 묶음을 사용한다. 자세한 설정은 [모델 ID별 계약](contracts/model-ids.md)을 참고한다.

실제 CUDA에서 ID 기본값·명시값·YAML 덮어쓰기/제거·검증 실패 원자성·배치/개별/간격 전달·동일 엔진 직렬 실행·ID별 결과 교체·누락/오류 정리·공유 사전 격리·Overlay 전체/단일 선택·ID별 이전 박스·전체 결과 누락·직렬 비동기 결과 보존을 확인한다. 기존 추론·전후처리·Overlay·좌표 복원·보고·비동기·프레임 해제 회귀와 후처리 벤치마크 수치 비교도 실행한다.

검증 결과: 모델 ID 13개·전후처리 7개·Overlay 5개·TensorRT 추론 28개·보고 14개·Async 38개·프레임 해제 6개·최적화 후처리 4개·최적화 전처리 3개·좌표 변환 3개, 총 121개가 통과했다. 후처리 벤치마크는 `--iterations 1`로 4개 구성의 이전 HEAD와 GPU 탐지 수치가 일치함을 확인했다. 반복 횟수가 적어 성능 결론에는 사용하지 않는다. `git diff --check`도 통과했다. 수렴 점검에서 FR-018~021·SC-010 및 계획·계약의 남은 구현 차이는 없다.

## 내장 모듈 파일명 변경 검증 (2026-10-11)

현재 가져오기 경로는 `pipeworks.embedded.tensor_rt_pre_process`다. 패키지 재수출과 직접 가져오기가 같은 클래스를 제공함을 확인했다. 옛 내장 파일은 없고 소스·예제·테스트·도구에 옛 import가 남지 않았다.

좌표 복원 3개·전처리 최적화 3개·전후처리 7개 검증이 통과했다. `tools/benchmark_preprocess.py --iterations 1`도 실행해 과거 HEAD 경로 조회와 RGB/NV12 6개 구성의 수치 비교가 통과했다. `git diff --check`는 통과했다. 수렴 점검에서 FR-017·SC-009의 남은 차이는 없다. 이전에 확인한 옛 예제 모듈 누락 테스트는 이번 내장 파일명 변경 범위에 포함하지 않는다.

## 좌표 복원 객체 검증 (2026-10-11)

`.venv/Scripts/python.exe -m unittest discover -s tests -p 'test_image_transform.py'`는 3개 검증이 통과했다. CPU·CUDA에서 세 리사이즈 방식·패딩 옵션·확대 제한·빈 결과·경계·추가 열·자료형·저장 공간과 불변 정보를 확인했다.

`test_tensor_rt_processing.py` 7개는 대체 객체의 복원 위임·CUDA 스트림·정리·실제 예제 엔진을 포함해 통과했다. `test_tensor_rt_postprocess_optimized.py` 4개, `test_tensor_rt_preprocess_optimized.py` 3개, `test_detection_report.py` 14개도 통과했다. `test_tensor_rt*.py` 전체는 54개 중 53개 통과하고 1개가 기존 옛 예제 모듈 누락으로 실패했다. HEAD에도 examples/step/tensor_rt_pre_process.py가 없으며 기존 테스트가 해당 경로를 가져온다. 이번 변경은 그 경로를 수정하지 않았다. `git diff --check`는 통과했다.

후처리는 변환 객체의 shape와 restore_boxes_만 사용한다. 상세 계약은 [이미지 좌표 복원 계약](contracts/transform.md)을 참고한다. 수렴 점검에서 FR-014~016·SC-008과 설계에 대한 미구현 차이는 없다.

## 범용 전처리 검증 절차

CUDA를 사용할 수 있는 기존 가상환경에서 다음 명령을 실행한다.

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -p test_tensor_rt_preprocess.py
.venv/Scripts/python.exe -m unittest discover -s tests -p test_tensor_rt_processing.py
```

새 검증은 구성 오류·설정 우선순위·세 가지 크기 변환·auto 최소 패딩·RGB/BGR·정규화·FP16/FP32·NCHW/NHWC·이름별 입력과 원본 저장 공간 독립성을 확인한다. 기존 전후처리 검증은 기본 계약·좌표 복원·비동기 프레임 수명·실제 엔진을 확인한다. 전체 및 관련 회귀 결과는 구현 완료 후 아래에 기록한다.

단일 예제는 TensorRTPreProcess → TensorRTInference(yolo11n.plan) → TensorRTPostProcess를 Async로 감싼다. 모델은 FP32 RGB 1×3×640×640 입력과 1×84×8400 출력의 COCO YOLO11 탐지 엔진이어야 한다.

TensorRTPostProcess 최상위 YAML 섹션에서 classes·confidence·iou·max_det·output_name을 설정한다. 기본 output_name은 output0이며 클래스 필터가 없으면 전체 클래스를 처리한다. 입력 색 변환·중앙 패딩·출력 NMS·좌표 복원은 GPU에서 수행한다. detections[model_id].boxes는 xyxy·conf·cls를 제공하고 detections[model_id].names는 클래스 ID별 이름을 제공한다. 추론 결과 누락은 해당 키의 None이다.

전처리·후처리 4개, BoxOverlay 5개, Async 35개 검증이 모두 통과했다. 실제 제공된 plan의 역직렬화·추론·후처리도 검증했으며 RTSP 네트워크 연결은 실행하지 않았다. 테스트에서는 실제 엔진 검증의 내부 대기 시간을 30초로 늘려 초기 로딩의 영향을 제외했다. 예제의 운영 제한 시간은 기존 20ms를 유지한다.

최종 수렴 점검에서 FR-001~004와 SC-001~002를 코드·예제·설정·검증에 대조했다. 추가 구현 작업은 없다.
## 스트림 분리 검증

전처리·직접 추론·후처리는 cuda_stream을 유지하며 같은 스트림에서 실행한다. 공유 배치는 입력 준비 이벤트를 내부 작업자 스트림에 연결한다. 후처리 성공·결과 누락·실패에서 model_input·model_output·복원 정보·model_id를 제거하며 cuda_stream은 보존한다. PyTorch 캐시는 강제로 비우지 않는다.

FR-005~006과 SC-003의 일관성을 분석했고 차단 충돌이 없었다. 실제 CUDA에서 스트림 핸들 분리·원본 영상 보존·좌표 복원·실패 후 버퍼 정리와 제공된 plan 추론을 확인했다. 전후처리 5개와 Async 35개 테스트가 모두 통과했다. 최종 수렴 점검에서 추가 구현 작업은 없다.

## 범용 전처리 구현 결과 (2026-10-10)

요청한 내장 경로와 embedded 내보내기를 제공하고 기존 예제 모듈은 같은 클래스를 재수출하도록 변경했다. NV12 변환은 공통 image 모듈로 옮겼으며 기존 YOLO 함수 이름과 계산을 보존했다. 생성자·YAML 옵션과 GPU 입출력 계약은 contracts/preprocess.md 및 공개 안내를 따른다.

새 검증은 구현 전 클래스 가져오기 실패를 확인한 뒤 구현 후 실제 CUDA에서 12개 모두 통과했다. 전후처리·프레임 수명·보고·Async·YOLO·오버레이·설정·핫스왑 관련 검증 162개는 160개 통과, 2개 건너뛰기였다. 제공된 TensorRT 예제 엔진 추론·후처리도 검증했다.

Windows 명명된 파이프 사용이 가능한 승인된 환경의 전체 검증은 322개 중 317개 통과, 3개 건너뛰기, 2개 오류였다. 오류는 기존 examples/02_multiple_stream_rtsp_style.py가 가져오는 step.post_process 모듈 누락이며 전처리 변경과 무관하다. 해당 기존 예제의 모듈 계약 변경은 이번 범위에 포함하지 않았다.

추가로 비균일 픽셀의 BGR 이미지에 Ultralytics CPU LetterBox와 새 GPU 전처리를 적용했다. auto=False/True의 출력 형상이 일치했고 RGB·FP16·정규화 출력의 최대 절대 차이는 0.0029296875였다. CPU uint8 보간과 GPU FP32 보간의 차이를 허용하는 수치 계약에 해당하며 비트 단위 일치를 주장하지 않는다.

git diff --check는 공백 오류 없이 통과했다. 구성 검증 실패 시 기존 옵션을 보존하고 출력 저장 공간이 원본과 독립적인 것을 검증했다.

## 전체 YAML 옵션 노출 검증

examples/config/stream.yml의 TensorRTPreProcess 섹션에 지원하는 15개 옵션을 모두 기본값으로 명시했다. 생성자 시그니처에서 읽은 옵션 이름 집합과 YAML 섹션의 키가 정확히 일치하고, configure에 섹션을 전달한 뒤 모든 구성 값이 기본 생성자와 같음을 확인했다. 한글 안내 주석을 추가했으며 git diff --check가 통과했다. 소스 변경과 GPU 추론은 필요하지 않았다.

## 예제 분리 검증 절차 (2026-10-11)

examples를 모듈 탐색 경로에 두고 step.tensor_rt_pre_process에서 가져온다. 제공 stream.yml에는 전처리 설정 없이 예제 생성자 기본값을 적용한다. 전처리·좌표 복원·후처리·모델 ID·보고·프레임 해제·CudaAsync 테스트와 참조·공개 위치·YAML·벤치마크 경로·공백 검증을 수행한다. 위 과거 내장 경로와 전체 YAML 노출 검증 기록은 이전 상태의 이력이다.

### 예제 분리 검증 결과

- 구현 전 공개 위치·제공 YAML 계약 테스트 2개가 예제 모듈 누락과 전처리 설정 잔존으로 실패하는 것을 확인했다.
- 이동한 examples/step/tensor_rt_pre_process.py는 이동 전 구현과 바이트 단위로 동일하다. 내장 모듈·내보내기는 제거했고 현재 코드의 내장 가져오기 참조는 없다. 제거 확인 테스트와 벤치마크의 과거 리비전 경로 문자열만 유지한다.
- 전처리·최적화·좌표 복원·후처리·모델 ID 테스트 39개가 통과했다. 실제 CUDA와 예제 TensorRT 엔진을 포함하며 건너뜀은 없다.
- 보고·프레임 해제·CudaAsync·Overlay·설정 기본값 회귀 74개 중 72개가 통과했다. 실패한 test_async의 원격 등록·모듈 없는 직렬화 테스트 2개는 모의 파이프라인에 development 속성이 없어 실패한다. HEAD의 main.py를 직접 로드한 재검증에서도 동일 오류가 재현되므로 이번 변경의 회귀가 아니다.
- Hotswap 회귀 30개가 통과했다. 별도로 실제 예제 파이프라인을 구성하고 _hot_steps의 예제 전처리 래핑과 모의 연결을 통한 중앙 프로세스 직렬화·모듈 없는 복원을 확인했다. 실제 RTSP 수신이나 중앙 서버 실행은 하지 않았다.
- 합계 143개 테스트 중 141개 통과, 기존 오류 2개다.
- 제공 YAML의 전처리 섹션만 제거했고 다른 섹션은 작업 시작 시 설정과 동일함을 확인했다. 예제 파이프라인은 전처리 생성자 기본값으로 구성된다.
- benchmark_preprocess.py --iterations 5로 RGB/NV12 각각 기본·평균/표준편차·FP16/NHWC의 6가지 HEAD 비교가 모두 수치 일치했다. 짧은 실행이므로 성능 개선 수치를 주장하지 않는다.
- 전처리 문서의 탐지·분류 생성자 예제를 실행했고 git diff --check를 통과했다.

재현 명령은 .venv/Scripts/python.exe -m unittest discover -s tests -p test_tensor_rt_preprocess.py와 해당 회귀 파일 패턴을 사용한다. 여러 모듈을 한 번에 실행할 때는 tests·src·examples를 모듈 탐색 경로에 추가하여 unittest 기본 로더로 불러온다.

## 표시·후처리 내부 설정 검증 절차

BoxOverlay와 TensorRTPostProcess를 직접 생성한 뒤 제공 YAML의 두 섹션 부재와 기본값·빈 구성 복원·클래스 목록 격리를 확인한다. 기존 GPU 혼합 클래스 입력에서 기본 [2] 필터를 검증하고 표시·좌표 복원·ID·보고 회귀와 예제 구성을 실행한다.

### 표시·후처리 내부 설정 검증 결과

- 두 계약 테스트가 구현 전에 직접 생성한 BoxOverlay의 옵션 누락과 YAML 섹션 잔존으로 실패하는 것을 확인했다.
- BoxOverlay 생성자 내부에 전체 ID·초록색·두께 2·이전 결과 유지 기본값을 모았다. TensorRTPostProcess 생성자 내부에 classes=[2]·confidence=0.25·iou=0.7·max_det=300·output_name=output0을 모았다. 빈 구성은 내부 기본값으로 복원하고 목록은 인스턴스 간 공유하지 않는다. 기존 configure 검증·명시적 설정과 GPU 실행 알고리즘은 유지한다.
- 후처리·Overlay·최적화·모델 ID·전처리·YOLO ID 회귀 54개와 별도 프로세스의 보고 회귀 14개가 모두 통과했다. 합계 68개이며 CUDA·실제 예제 TensorRT 엔진을 포함하고 건너뜀은 없다. 기본 혼합 클래스 입력에서 클래스 [2]만 남는 것을 검증했다.
- 같은 프로세스에서 모델 ID 검증 뒤 보고 검증을 실행하면 공유 배치 상태의 영향으로 실제 배치 출력 형식 검증 1개가 실패한다. HEAD의 두 예제 클래스 코드를 로드한 기존 구현에서도 같은 순서로 오류가 재현되며, 보고 테스트를 독립 실행하면 14개 모두 통과한다. 이번 변경으로 발생한 회귀로 판단하지 않는다.
- 단일 스트림 예제 생성과 두 단계의 기본값을 검증했다. 제공 YAML에서 두 섹션만 제거했고 다른 섹션의 값은 작업 시작 시 내용과 동일하다. 파일 끝의 빈 줄을 정리하고 git diff --check가 통과했다.
- 다중 스트림 예제 실행 검증은 기존 step.post_process 모듈 누락으로 제한된다. 해당 예제 및 누락 모듈은 이번 범위에서 수정하지 않았다.

재현: tests·src·examples를 탐색 경로에 두고 unittest 기본 로더로 test_box_overlay, test_tensor_rt_processing, test_tensor_rt_postprocess_optimized, test_tensor_rt_model_ids, test_tensor_rt_preprocess, test_yolo_model_ids를 함께 실행한다. 보고 테스트는 .venv/Scripts/python.exe -m unittest discover -s tests -p test_detection_report.py로 별도 실행한다.

## TensorRT 스트림 통일 검증

- 전처리·후처리·좌표 변환·모델 ID 관련 44개 테스트가 통과했다.
- 직접 추론·공유 배치·프레임 해제·비동기·보고 관련 93개 테스트 중 91개가 통과했다. 실제 TensorRT 엔진 실행과 프레임별 스트림 교체 검증을 포함한다.
- 나머지 2개는 기존 원격 실행 테스트의 SimpleNamespace.development 속성 누락으로 실패했다. 이번 스트림 변경 범위 밖이며 이전에도 확인된 실패다.
- 세 TensorRT 구현과 HTML 공통 데이터에 model_cuda_stream 또는 current_model_stream 참조가 없음을 확인했다. git diff --check는 통과했다.
- 환경에 Ruff 모듈이 없어 Ruff 포맷 검사는 실행하지 못했다.
- 수렴 점검: FR-031~034와 SC-014~015의 구현·테스트·문서 반영을 확인했다. 현재 변경 범위에서 추가 구현 작업은 없다.

## 원격 실행 테스트 구성 수정 검증

두 원격 실행 테스트의 가짜 파이프라인에 development=False를 추가했다. 대상 2개 테스트와 test_async.py 전체 38개 테스트가 통과했다. git diff --check도 통과했다. 앞선 스트림 통일 검증에서 기록한 development 속성 누락 오류는 이번 수정으로 해결했다.

## CudaAsync 내부 스트림 전달 검증

- 내부 작업 컨텍스트의 cuda_stream을 GPU별 작업자 스트림으로 교체하며 원래 스트림 속성과 속성 부재를 결과 반영 시 복원한다. 입력 준비 이벤트 대기와 작업 완료 동기화는 유지한다.
- YOLO도 cuda_stream을 사용하고 execution의 모델 스트림 ContextVar 및 조회·범위 함수를 제거했다. 이 설계가 앞선 별도 범위 유지 결정을 대체한다.
- 비동기·프레임 해제·전처리·처리·YOLO 모델 ID·보고 91개 및 TensorRT 직접·배치·모델 ID·최적화 55개 테스트가 모두 통과했다.
- 소스·테스트·문서에 current_model_stream 및 _model_stream_scope 참조가 없고 git diff --check가 통과했다.
