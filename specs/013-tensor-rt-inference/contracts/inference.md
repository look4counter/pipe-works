# 추론 단계 계약

`TensorRTInference(model_path: Path)`를 embedded에서 가져온다. `configure`는 `gpu_id=0`, `inference_interval=1`을 검증한다. `process`는 입력 객체와 순서를 유지한다.

입력이 하나면 `context.model_input`에 GPU 텐서를 넣는다. 입력이 여러 개면 모든 실제 입력 이름과 GPU 텐서를 사전으로 넣는다. 입력 값·형상·자료형은 전처리 단계의 책임이며 자료형·GPU 이동·정규화·리사이즈를 수행하지 않는다.

성공 출력은 단일 출력에서도 `{실제 출력 이름: GPU 텐서}`다. 실패·시간 초과·간격·작업자 사용 중에는 `model_output=None`이며 기존 `model_input`과 영상 속성을 보존한다.

`model.engine` 옆 `model.yml`의 `timeout`은 밀리초이며 기본 5다. `plugins`는 외부 공유 라이브러리 경로 목록이며 상대 경로는 그 YAML 디렉터리 기준이다. 배치 크기는 입력 텐서에서 결정하며 `max_batch_size`로 요청을 모으지 않는다. CPU 바인딩·벡터화 포맷 및 지원하지 않는 자료형은 실패로 알린다. 동적 입력은 프로파일 0을 사용한다.
## 최신 동기 실행 계약

과거 비동기·자체 제한 시간 계약은 동기 실행으로 대체한다. 내부 작업자·요청 큐는 없고 GPU 완료 후 결과를 전달한다. 연속 입력은 복제하지 않으며 비연속 입력만 연속화한다. 실패는 예외로 전파하고 간격으로 건너뛴 입력만 model_output=None이다. 모델 YAML의 timeout은 읽지 않고 plugins만 유지한다. 시간 제한과 오류 통과는 공통 Async로 적용한다.
## 선택적 배치 계약

생성자의 batch 키워드는 기본 False이고 불리언만 허용한다. True이면 local_tensor_rt의 공유 요청 수집을 사용한다. 개별 요청은 배치 크기 1이며 입력·출력 배치 축은 0이다. 간격·gpu_id·GPU 출력·통계는 유지한다. 오류는 전파하고 수집 기한은 모델 YAML의 timeout이며 추론 제한이 아니다.

## 예제 NMS 원시 출력 소비 계약

TensorRTPostProcess는 model_output의 요청별 prediction을 복제하지 않고 NMS에 넘기며 좌표 제자리 변환을 허용한다. 원시 출력은 이후 다시 사용하지 않고 정리한다. input.detections의 GPU 박스·클래스·신뢰도·이름은 유지하며 BoxOverlay는 원시 출력이 아니라 detections와 frame을 사용한다. 다른 소비자가 원시 출력을 보존해야 하는 구성은 이 예제의 단독 소비 계약에 해당하지 않는다.
