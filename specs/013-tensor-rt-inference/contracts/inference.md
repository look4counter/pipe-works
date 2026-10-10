# 추론 단계 계약

## 영상별 프로파일 최신 계약

stream.yml의 TensorRTInference 아래 profile_index(기본 0, 불리언 제외 음수가 아닌 정수)를 설정한다. 실행 중 설정 변경은 다음 입력부터 적용된다. local_tensor_rt.infer는 profile_index=0 키워드 인자를 받으며 공유 수집·세션·실패 정리를 프로파일별로 분리한다. 모델 동명 YAML은 plugins·max_batch_size·timeout_ms를 사용한다. 이전 timeout은 timeout_ms로 변경하고 이전 모델 profile_index는 클래스명 설정으로 이동해야 하며 잘못된 위치와 이름은 안내 오류로 거부한다. 이 계약이 이전 모델 YAML 프로파일 계약을 대체한다.

## 모델 YAML 실행 옵션 계약

엔진과 동명 .yml에 profile_index: 0과 plugins: []를 지정할 수 있다. 파일과 항목 생략은 이 기본값과 같다. profile_index는 불리언을 제외한 음수가 아닌 정수이며 엔진 프로파일 수보다 작아야 한다. plugins는 비어 있지 않은 경로 문자열 목록이며 상대 경로 기준은 YAML 디렉터리다. 두 모드는 역직렬화 전 플러그인 로딩과 입력 형상 설정 전 실행 스트림의 프로파일 선택을 보장한다. 잘못된 설정·프로파일 선택 실패·플러그인 누락은 예외로 전달한다. 실행을 다시 시작해야 변경을 반영하며 공유 작업자 설정을 변경하려면 프로세스를 다시 시작한다. 이 계약이 과거 프로파일 0 고정 및 plugins만 읽는 설명을 대체한다.

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
# 프레임 간격 공개 계약 갱신

클래스명 YAML과 공개 속성은 `inference_interval_frame`을 사용한다. 생략 시 1, 값은 불리언을 제외한 1 이상의 정수다. 기존 `inference_interval`이 설정에 있으면 새 키의 동시 존재 여부와 무관하게 ValueError로 새 이름을 안내하며 상태를 변경하지 않는다. 간격 3은 개별·배치 모드 모두 1·4·7번째 입력을 선택한다. 기존 설명의 간격 이름은 이 계약으로 대체한다.
