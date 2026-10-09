# 구현 계획

examples/step/box_overlay.py에서 박스를 GPU 복제하여 보관한다. 네 테두리 사각형의 코너를 2차원 차분 배열에 scatter_add하고 누적합으로 테두리 마스크를 만든다. 박스 수에 비례한 영상 크기 임시 배열을 만들지 않는다. NV12 색차는 각 2×2 휘도 마스크의 논리합으로 적용한다. 스트림 간 보관 박스 준비 이벤트와 record_stream으로 수명을 보호한다. 기존 tests/test_box_overlay.py에 CPU 접근 금지를 추가하고 실제 CUDA 회귀를 실행한다.
