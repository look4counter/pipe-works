# 데이터 모델

모델 배치 설정은 max_batch_size와 max_batch_wait_ms로 구성한다. 내부 수집 시간은 초로 변환한다. TensorRT 세션은 모델 경로와 프로파일 번호를 보유하고 외부 플러그인 핸들을 보관하지 않는다.
