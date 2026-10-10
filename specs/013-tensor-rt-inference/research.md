# TensorRT 추론 연구

## 영상별 프로파일과 시간 명칭 결정

- 결정: 모델 파일이 같은 요청은 작업자를 공유하되 GPU·프로파일별 세션을 분리한다. 근거: 영상별 프로파일을 동일 형상 요청 수집에도 반영해야 하고 한 프로파일 실패가 다른 프로파일 세션을 폐기해서는 안 된다.
- 결정: 개별 경로는 실행 중 변경을 새 세션으로 적용한다. 기존 세션의 프로파일을 바꾸는 대안은 바인딩·출력 할당기 상태를 다시 초기화해야 하므로 기존 GPU 변경 재생성 방식을 따른다.
- 결정: timeout_ms는 수집 대기이며 내부 초 단위 수집 계약은 유지한다. 이전 키와 이전 모델 프로파일은 안내 오류로 거부하여 기본값으로 조용히 실행되는 설정 실수를 방지한다. 기술 미확정 사항은 없다.

## 모델 YAML 프로파일 선택 조사

- 실제 검증: TensorRT 10.10의 set_input_shape는 선택 프로파일 범위 밖 형상에도 성공할 수 있고 이후 infer_shapes에서 오류가 발생한다. 입력의 최소·최대 범위를 get_tensor_profile_shape로 먼저 확인하여 명확한 선택 번호와 함께 예외를 반환한다.

- 결정: 공통 설정 검증으로 개별·배치 양쪽에 기본 프로파일 0과 외부 플러그인 목록을 전달한다. 중복 검증 구현은 이름·기본값 차이를 만들 수 있어 채택하지 않는다.
- 결정: 설치된 TensorRT 10.10.0.31의 공식 Python API 설명을 확인했다. set_optimization_profile_async(profile_index, stream_handle)는 성공 불리언을 반환하고 선택 작업과 추론 사이 동기화가 필요하다. 같은 실행 스트림에서 선택·바인딩·추론을 순서대로 제출한다.
- 결정: get_tensor_format(name, profile_index) 오버로드를 사용하여 선택된 프로파일의 포맷을 검증한다. 엔진 num_optimization_profiles로 범위를 확인하고 오류에는 번호를 포함한다.
- 미확정 기술 사항은 없다. 외부 최신 문서는 버전 경로가 리다이렉트되어 설치된 프로젝트 버전의 공식 API 설명을 기준으로 삼았다.

## 프레임 간격 명칭 결정

- 결정: 새 이름은 `inference_interval_frame`이며 기존 키는 변경 안내 오류로 거부한다.
- 근거: 기존 YoloDetect의 동일 명칭·이전 키 거부 계약을 재사용하여 설정 실수를 방지한다. 외부 기술 조사가 필요한 미확정 사항은 없다.
- 검토 대안: 이전 키 별칭 지원은 두 이름을 남기므로 채택하지 않는다. 선택 간격과 결과는 그대로 유지한다.

- 결정: TensorRT 10의 이름 기반 I/O와 `execute_async_v3`에 PyTorch CUDA 스트림 핸들을 전달한다. 근거: 이름을 고정하지 않고 GPU 주소를 연결할 수 있다. 대안인 YOLO 예측기와 NumPy 버퍼는 추론 전용·CPU 복사 금지 계약에 맞지 않는다. [공식 Python 안내](https://docs.nvidia.com/deeplearning/tensorrt/10.x.x/inference-library/python-api-docs.html)
- 결정: 출력 할당기로 데이터 의존 크기를 처리하며 모든 입출력은 DEVICE·LINEAR로 제한한다. 근거: 일반 연속 GPU 텐서로 호스트 바인딩과 벡터화 저장 포맷을 그대로 연결할 수 없다. [엔진 API](https://docs.nvidia.com/deeplearning/tensorrt/latest/_static/python-api/infer/Core/Engine.html), [실행 컨텍스트 API](https://docs.nvidia.com/deeplearning/tensorrt/latest/_static/python-api/infer/Core/ExecutionContext.html)
- 결정: 표준 플러그인 초기화, Runtime의 엔진 포함 실행 코드 허용 및 외부 레지스트리 라이브러리 로딩을 사용한다. 근거: 플러그인 포함 엔진이 사용자 요구이며 외부 라이브러리 핸들의 수명을 보장해야 한다. [플러그인 안내](https://docs.nvidia.com/deeplearning/tensorrt/10.x.x/inference-library/extending-custom-layers.html), [Runtime API](https://docs.nvidia.com/deeplearning/tensorrt/latest/_static/python-api/infer/Core/Runtime.html)
- 결정: 단일 작업자 슬롯은 기존 비동기 YOLO 기반을 재사용하고 TensorRT 실행은 별도 루프로 분리한다. 근거: 오래 걸리는 초기화·플러그인 호출도 영상 전달과 분리하며 동일 인스턴스의 영구 정지에 작업자를 추가하지 않는다.
- 환경: TensorRT는 프로젝트 의존성에 있으나 현재 가상환경에는 설치되어 있지 않다. 모의 API와 실제 GPU 계약 검증을 먼저 수행하고 실제 엔진 검증은 실행 환경 조건을 명시한다.
