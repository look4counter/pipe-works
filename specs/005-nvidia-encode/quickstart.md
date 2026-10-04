# 검증 안내: NVIDIA 비디오 인코딩

## 준비

프로젝트 의존성을 설치한다. 실제 인코딩 검증에는 NVIDIA GPU와 해당 드라이버가 필요하다.

## 확인 항목

1. 모의 인코더가 빈 목록을 반환할 때 출력 컨텍스트가 없는지 확인한다.
2. 사전 항목 둘 이상을 반환할 때 각 항목이 PyAV 패킷으로 나오고 PTS·DTS가 증가하는지 확인한다.
3. 중첩 사전 또는 목록의 압축 바이트와 `EndEncode()`의 잔여 결과를 확인한다.
4. 압축 바이트가 없는 결과에서 명시적인 오류가 발생하는지 확인한다.
5. `python -m py_compile src/pipeworks/embedded/nvidia_encode.py`와 `python -m unittest discover -s tests -p test_rtsp_publish.py`를 실행한다.

실제 GPU와 RTSP 서버를 이용한 종단 간 결과는 현재 모의 검증에 포함되지 않는다.
