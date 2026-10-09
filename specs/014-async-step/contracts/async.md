# CudaAsync 계약

CudaAsync(*steps, timeout_ms=5)는 하나 이상의 Step을 입력당 출력 하나로 연결한다. 모듈은 pipeworks.embedded.cuda_async이며 구성은 timeout_ms만 받는다. 내부 설정은 클래스명 최상위 YAML 섹션에서 받으며 코드·설정 핫스왑과 중앙 직렬화를 유지한다.

정상 완료에는 같은 원본 컨텍스트에 결과를 적용한다. 바쁠 때 새 입력은 제출하지 않고 그대로 전달한다. 타임아웃에는 요청 전체 완료 또는 사용 종료가 확인된 원본만 전달하고 나머지 프레임은 폐기한다. 보호 복사와 GPU 완료 추가 대기는 없다. 늦은 결과는 폐기하고 미시작 Step은 건너뛴다. 원본 참조는 GPU 정리 완료까지 유지한다.

release_frame(ready_event=...)은 별도 RGB 생성 이후 원본 영상 사용 종료를 알린다. 단일·복수 단계에서 적용하며 같은 CudaAsync의 이후 단계는 원본을 다시 사용하지 않는다. 이벤트가 있으면 query 완료를 확인한다. 기존 release_input은 모든 공유 입력 종료로 단일 Step에서만 적용한다. 두 신호는 CudaAsync 밖에서 무동작이다.

공유 입력은 읽기 전용이며 결과는 속성 교체 또는 새 데이터로 반환한다. 원본을 수정하는 BoxOverlay는 CudaAsync 바깥에 둔다. 영상만 해제한 경우 다른 공유 데이터도 변경하지 않는다. 다중 입력·다중 출력 및 소스 Step은 지원하지 않는다.

current_model_stream()으로 공통 스트림을 조회한다. input.cuda_stream은 영상·인코딩용으로 유지한다. YOLO 배치는 독립 RGB와 완료 이벤트를 제출하며 local_yolo 직접 NV12 호출도 유지한다. RGB 생성·리사이즈·배치 stack 등 모델 연산에 필요한 할당은 이 보호 복사 제거의 대상이 아니다.
