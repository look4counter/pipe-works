# TensorRTBackend와 엔진 세션

구현: src/pipeworks/yolo_backends/tensorrt.py. 일반 앱은 YoloInference(model_path, backend=Backend.TENSORRT, profile_index=0)를 사용합니다. 해당 Step과 공유 작업자는 _EngineSession을 통해 프로파일·자원 수명을 관리합니다.

TensorRTBackend(model_path, gpu_id)는 공통 실행부 인터페이스용 어댑터입니다. 모델 옆 .yml의 plugins를 읽고 기본 프로파일 세션을 생성합니다. infer(inputs)는 지정 GPU의 현재 CUDA 스트림으로 세션을 실행하고 close()는 세션을 닫습니다. 이 클래스를 직접 호출하면 YoloInference의 입력 준비·전체 동기화·설정 감시를 대신 구현해야 하므로 일반 연결은 Step을 사용합니다.

엔진의 실제 입력 이름·자료형·형상과 동적 프로파일 범위를 검사하고 출력 이름별 GPU 텐서를 반환합니다. 단일 입력 엔진은 텐서 자체를, 다중 입력은 모든 이름을 포함한 사전을 받습니다. GPU LINEAR 바인딩을 지원하며 CPU 형상 바인딩·지원하지 않는 자료형·저장 형식은 오류입니다. 고정 메타데이터는 세션에 캐시하고 데이터 의존 출력 크기는 allocator로 처리합니다.

일반 엔진과 Ultralytics JSON 메타데이터 헤더가 붙은 엔진을 읽습니다. 표준 플러그인을 초기화하고 외부 라이브러리를 역직렬화 전에 로드합니다. 모델 파일·TensorRT·플러그인·GPU의 호환성은 실행 환경에 맞아야 합니다. 엔진 생성·변환은 수행하지 않습니다.

_load_model_config·_engine_settings·_EngineSession·출력 allocator 등 밑줄 이름은 내부 구현입니다. 앱에서 세션을 직접 만들기보다 [TensorRT 모델 설정](../embedded/tensor_rt_inference.md)과 [공통 실행부 계약](../yolo_backend.md)을 사용합니다.
