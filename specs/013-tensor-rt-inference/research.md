# TensorRT 추론 연구

- 결정: TensorRT 10의 이름 기반 I/O와 `execute_async_v3`에 PyTorch CUDA 스트림 핸들을 전달한다. 근거: 이름을 고정하지 않고 GPU 주소를 연결할 수 있다. 대안인 YOLO 예측기와 NumPy 버퍼는 추론 전용·CPU 복사 금지 계약에 맞지 않는다. [공식 Python 안내](https://docs.nvidia.com/deeplearning/tensorrt/10.x.x/inference-library/python-api-docs.html)
- 결정: 출력 할당기로 데이터 의존 크기를 처리하며 모든 입출력은 DEVICE·LINEAR로 제한한다. 근거: 일반 연속 GPU 텐서로 호스트 바인딩과 벡터화 저장 포맷을 그대로 연결할 수 없다. [엔진 API](https://docs.nvidia.com/deeplearning/tensorrt/latest/_static/python-api/infer/Core/Engine.html), [실행 컨텍스트 API](https://docs.nvidia.com/deeplearning/tensorrt/latest/_static/python-api/infer/Core/ExecutionContext.html)
- 결정: 표준 플러그인 초기화, Runtime의 엔진 포함 실행 코드 허용 및 외부 레지스트리 라이브러리 로딩을 사용한다. 근거: 플러그인 포함 엔진이 사용자 요구이며 외부 라이브러리 핸들의 수명을 보장해야 한다. [플러그인 안내](https://docs.nvidia.com/deeplearning/tensorrt/10.x.x/inference-library/extending-custom-layers.html), [Runtime API](https://docs.nvidia.com/deeplearning/tensorrt/latest/_static/python-api/infer/Core/Runtime.html)
- 결정: 단일 작업자 슬롯은 기존 비동기 YOLO 기반을 재사용하고 TensorRT 실행은 별도 루프로 분리한다. 근거: 오래 걸리는 초기화·플러그인 호출도 영상 전달과 분리하며 동일 인스턴스의 영구 정지에 작업자를 추가하지 않는다.
- 환경: TensorRT는 프로젝트 의존성에 있으나 현재 가상환경에는 설치되어 있지 않다. 모의 API와 실제 GPU 계약 검증을 먼저 수행하고 실제 엔진 검증은 실행 환경 조건을 명시한다.
