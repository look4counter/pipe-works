# 모델 설정 계약

YoloInference(model_path, *, batch=False, gpu_id=0, id=None, backend, profile_index=0)

동명 .yml의 max_batch_size와 max_batch_wait_ms를 사용한다. 파일 미존재 기본값은 1과 0이다. config_path는 받지 않는다. 외부 플러그인은 지원하지 않는다.
