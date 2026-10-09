# 구현 계획

src/pipeworks/batch_collector.py에 모델 독립 collect_batch 함수를 두고 기존 큐·보류 deque·크기·초 단위 기한을 받는다. 호환 키와 수신 시각은 호출자가 함수로 제공한다. local_yolo의 기존 _next_batch는 공통 호출로 대체하고 GPU 코드·결과 전달을 보존한다. tests/test_local_yolo.py의 수집 검증을 새 모듈에 이전하고 YOLO 회귀를 실행한다.
