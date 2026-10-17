# 생성자 계약

YoloInference(model_path, *, config_path=None, batch=False, gpu_id=0, id=None, backend, profile_index=0)

설정 경로는 생성자 전용이며 문자열 또는 Path를 받는다. None은 기본 설정을 뜻한다. 명시 파일이 없으면 오류를 낸다. TensorRT 플러그인의 상대 경로는 모델 디렉터리 기준이다. 외부 사용자 백엔드의 생성자 인자는 변경하지 않는다.
