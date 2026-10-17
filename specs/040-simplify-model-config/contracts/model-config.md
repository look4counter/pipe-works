# 모델 설정 계약

max_batch_wait_ms는 bool을 제외한 유한한 0 이상의 밀리초다. 무설정 기본값은 0이다. max_batch_size 기본값은 1이다. 비 TensorRT는 파일 지정 시 두 키를 모두 명시한다. plugins는 더 이상 지원하지 않으며 라이브러리를 로드하지 않는다. RTSP와 CudaAsync의 timeout_ms는 유지한다.
