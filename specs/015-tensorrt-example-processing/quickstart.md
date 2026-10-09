# 검증과 사용

단일 예제는 TensorRTPreProcess → TensorRTInference(yolo11n.plan) → TensorRTPostProcess를 Async로 감싼다. 모델은 FP32 RGB 1×3×640×640 입력과 1×84×8400 출력의 COCO YOLO11 탐지 엔진이어야 한다.

TensorRTPostProcess 최상위 YAML 섹션에서 classes·confidence·iou·max_det·output_name을 설정한다. 기본 output_name은 output0이며 클래스 필터가 없으면 전체 클래스를 처리한다. 입력 색 변환·중앙 패딩·출력 NMS·좌표 복원은 GPU에서 수행한다. detections.boxes는 xyxy·conf·cls를 제공하고 detections.names는 클래스 ID별 이름을 제공한다. 추론 결과 누락은 detections=None이다.

전처리·후처리 4개, BoxOverlay 5개, Async 35개 검증이 모두 통과했다. 실제 제공된 plan의 역직렬화·추론·후처리도 검증했으며 RTSP 네트워크 연결은 실행하지 않았다. 테스트에서는 실제 엔진 검증의 내부 대기 시간을 30초로 늘려 초기 로딩의 영향을 제외했다. 예제의 운영 제한 시간은 기존 20ms를 유지한다.

최종 수렴 점검에서 FR-001~004와 SC-001~002를 코드·예제·설정·검증에 대조했다. 추가 구현 작업은 없다.
## 스트림 분리 검증

전처리·후처리는 별도 model_cuda_stream을 사용하고 원본 cuda_stream은 유지한다. 영상 준비 이벤트 이후 전처리하며 TensorRTInference는 모델 스트림을 입력 생산자로 확인한다. 각 처리 완료를 확인해 결과 수명을 보장한다. 후처리 성공·결과 누락·실패에서 model_input·model_output·복원 정보·모델 스트림 참조를 제거한다. PyTorch 캐시는 강제로 비우지 않는다.

FR-005~006과 SC-003의 일관성을 분석했고 차단 충돌이 없었다. 실제 CUDA에서 스트림 핸들 분리·원본 영상 보존·좌표 복원·실패 후 버퍼 정리와 제공된 plan 추론을 확인했다. 전후처리 5개와 Async 35개 테스트가 모두 통과했다. 최종 수렴 점검에서 추가 구현 작업은 없다.
