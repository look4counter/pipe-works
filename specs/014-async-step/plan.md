# 구현 계획: CudaAsync 무복사 전달

## 기술 문맥과 범위

Python·PyTorch CUDA·Ultralytics·TensorRT를 사용한다. 기존 스레드 슬롯, 연결 반복자, 핫스왑, 클래스명 YAML 설정과 중앙 직렬화를 유지한다. 작업 범위는 execution.py, embedded/cuda_async.py, embedded/yolo_detect.py, local_yolo.py, 예제 TensorRTPreProcess 및 관련 문서·테스트다. 사용자 예제 파이프라인과 TensorRT 배치 옵션은 변경하지 않는다.

## 설계

1. CudaAsync의 _snapshot·deepcopy·복사 이벤트 목록·정리 스레드를 제거한다. DLPack 메모리 공유와 원본 참조·입력 준비 이벤트는 유지한다.
2. execution.py에 요청별 release_frame과 _frame_scope를 추가한다. 기존 release_input은 단일 Step 전체 입력 계약으로 유지한다. 복수 Step에서도 영상 신호를 연결하고 뒤 단계의 원본 재사용 금지를 문서화한다.
3. 타임아웃 시 요청 전체 완료 또는 사용 종료 이벤트 query 성공이면 원본을 전달한다. 아직 사용 중이거나 신호가 없으면 해당 프레임을 폐기한다. 추가 기다림·복사·결과 병합은 없다. 바쁠 때 후속 입력 통과는 유지한다.
4. YOLO 개별 _predict는 NV12→RGB 직후 이벤트를 기록해 신호를 보낸다. 이후 리사이즈·추론·좌표 복원은 RGB만 사용한다.
5. YOLO 배치는 생산자 이벤트를 기다린 뒤 RGB를 생성한다. NV12 clone 대신 RGB·준비 이벤트를 local_yolo에 제출한다. local_yolo는 FP32 CHW RGB와 기존 uint8 NV12를 받아 RGB에는 중복 변환하지 않는다. 배치 stack은 유지한다.
6. TensorRTPreProcess도 NV12→RGB 직후 신호를 보내며 후속 연산은 별도 텐서를 사용한다. 기존 전처리 종료 동기화는 유지한다.

## 검증 계획

회귀를 먼저 갱신해 기존 보호 복사 구현의 실패를 확인한다. CPU 차단 작업과 가짜 query 이벤트로 완료·미완료·조회 오류·오래된 문맥·복수 신호·정리를 확인한다. 실제 CUDA에서 CudaAsync의 clone 금지, DLPack 수명, RGB 원본 격리와 YOLO 배치·TensorRT 전처리 신호를 확인한다. test_async·test_yolo_detect·test_yolo_batch·test_local_yolo·test_tensor_rt_processing 및 TensorRT 추론·배치 회귀를 실행한다.

## 헌법 및 분석

헌법은 미작성 템플릿이므로 검사를 생략한다. Markdown은 한글로 작성한다. 과거 복사·단계 설정 계약은 명세에 대체 관계를 명시해 모순을 없앤다. 작업 번호는 기존 목록에 이어 추가한다.
