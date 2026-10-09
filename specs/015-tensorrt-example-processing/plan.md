# 구현 계획

examples/step/tensor_rt_pre_process.py와 tensor_rt_post_process.py의 빈 파일을 구현한다. NV12 색 변환은 기존 local_yolo GPU 함수를 재사용하고 torch 보간·패딩으로 입력과 복원 정보를 만든다. 후처리는 Ultralytics NMS와 Boxes를 이용하여 BoxOverlay와 동일한 감지 계약을 제공한다. 결과는 GPU에 유지하고 원본 orig_img는 만들지 않는다. BoxOverlay는 Async 타임아웃으로 detections 속성이 없는 입력도 결과 누락으로 처리한다.

examples/01_single_stream_rtsp_style.py의 클래스명·plan 경로·불필요 batch 인자를 수정하고 examples/config/stream.yml에 두 단계 설정을 추가한다. tests/test_tensor_rt_processing.py는 실제 CUDA 합성 입력과 출력을 검증한다. test_box_overlay.py의 예제 순서 검증은 TensorRT 경로에 맞춘다. 실제 엔진 추론도 가능한 환경에서 검증한다. 헌법은 미작성 템플릿으로 원칙 검사를 생략한다.
## 스트림·버퍼 후속 계획

전처리 반복자에 장치별 모델 CUDA 스트림을 보관하고 영상 생산 완료 이벤트를 기록·대기한 뒤 변환한다. model_cuda_stream을 입력 생산자 정보로 전달하며 전처리 완료도 확인한다. TensorRTInference는 해당 스트림을 우선 사용한다. 후처리는 모델 스트림에서 NMS·복원을 수행하고 finally에서 완료 확인·임시 속성 및 지역 참조를 정리한다. 예외·출력 누락도 같은 정책을 사용한다. tests/test_tensor_rt_processing.py에 분리·정리 검증을 추가하고 실제 plan·Async를 검증한다.
