# 검증과 사용

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

TensorRTPostProcess 최상위 YAML 섹션에서 classes·confidence·iou·max_det·output_name을 설정한다. 기본 output_name은 output0이며 클래스 필터가 없으면 전체 클래스를 처리한다. 입력 색 변환·중앙 패딩·출력 NMS·좌표 복원은 GPU에서 수행한다. detections.boxes는 xyxy·conf·cls를 제공하고 detections.names는 클래스 ID별 이름을 제공한다. 추론 결과 누락은 detections=None이다.

전처리·후처리 4개, BoxOverlay 5개, Async 35개 검증이 모두 통과했다. 실제 제공된 plan의 역직렬화·추론·후처리도 검증했으며 RTSP 네트워크 연결은 실행하지 않았다. 테스트에서는 실제 엔진 검증의 내부 대기 시간을 30초로 늘려 초기 로딩의 영향을 제외했다. 예제의 운영 제한 시간은 기존 20ms를 유지한다.

최종 수렴 점검에서 FR-001~004와 SC-001~002를 코드·예제·설정·검증에 대조했다. 추가 구현 작업은 없다.
## 스트림 분리 검증

전처리·후처리는 별도 model_cuda_stream을 사용하고 원본 cuda_stream은 유지한다. 영상 준비 이벤트 이후 전처리하며 TensorRTInference는 모델 스트림을 입력 생산자로 확인한다. 각 처리 완료를 확인해 결과 수명을 보장한다. 후처리 성공·결과 누락·실패에서 model_input·model_output·복원 정보·모델 스트림 참조를 제거한다. PyTorch 캐시는 강제로 비우지 않는다.

FR-005~006과 SC-003의 일관성을 분석했고 차단 충돌이 없었다. 실제 CUDA에서 스트림 핸들 분리·원본 영상 보존·좌표 복원·실패 후 버퍼 정리와 제공된 plan 추론을 확인했다. 전후처리 5개와 Async 35개 테스트가 모두 통과했다. 최종 수렴 점검에서 추가 구현 작업은 없다.

## 범용 전처리 구현 결과 (2026-10-10)

요청한 내장 경로와 embedded 내보내기를 제공하고 기존 예제 모듈은 같은 클래스를 재수출하도록 변경했다. NV12 변환은 공통 image 모듈로 옮겼으며 기존 YOLO 함수 이름과 계산을 보존했다. 생성자·YAML 옵션과 GPU 입출력 계약은 contracts/preprocess.md 및 공개 안내를 따른다.

새 검증은 구현 전 클래스 가져오기 실패를 확인한 뒤 구현 후 실제 CUDA에서 12개 모두 통과했다. 전후처리·프레임 수명·보고·Async·YOLO·오버레이·설정·핫스왑 관련 검증 162개는 160개 통과, 2개 건너뛰기였다. 제공된 TensorRT 예제 엔진 추론·후처리도 검증했다.

Windows 명명된 파이프 사용이 가능한 승인된 환경의 전체 검증은 322개 중 317개 통과, 3개 건너뛰기, 2개 오류였다. 오류는 기존 examples/02_multiple_stream_rtsp_style.py가 가져오는 step.post_process 모듈 누락이며 전처리 변경과 무관하다. 해당 기존 예제의 모듈 계약 변경은 이번 범위에 포함하지 않았다.

추가로 비균일 픽셀의 BGR 이미지에 Ultralytics CPU LetterBox와 새 GPU 전처리를 적용했다. auto=False/True의 출력 형상이 일치했고 RGB·FP16·정규화 출력의 최대 절대 차이는 0.0029296875였다. CPU uint8 보간과 GPU FP32 보간의 차이를 허용하는 수치 계약에 해당하며 비트 단위 일치를 주장하지 않는다.

git diff --check는 공백 오류 없이 통과했다. 구성 검증 실패 시 기존 옵션을 보존하고 출력 저장 공간이 원본과 독립적인 것을 검증했다.

## 전체 YAML 옵션 노출 검증

examples/config/stream.yml의 TensorRTPreProcess 섹션에 지원하는 15개 옵션을 모두 기본값으로 명시했다. 생성자 시그니처에서 읽은 옵션 이름 집합과 YAML 섹션의 키가 정확히 일치하고, configure에 섹션을 전달한 뒤 모든 구성 값이 기본 생성자와 같음을 확인했다. 한글 안내 주석을 추가했으며 git diff --check가 통과했다. 소스 변경과 GPU 추론은 필요하지 않았다.
