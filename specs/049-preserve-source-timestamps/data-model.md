# 데이터 모델

입력 컨텍스트 pts는 정수, time_base는 양의 유리수이며 생략 시 video_stream.time_base를 사용한다. duration은 0 이상의 정수이며 기본값은 0이다.

시각 큐는 입력당 (pts, time_base, duration) 튜플을 저장하고 비어 있지 않은 출력당 하나씩 소비한다. 세션 해제 시 비운다.

출력 pts=dts=원본 pts이며 time_base와 duration을 유지한다. 영상 정보는 패킷과 같은 시간 기준과 설정 fps를 갖는다.

잠금 버퍼 소유자는 기존 포인터·이벤트·풀 참조에 pts를 추가한다. 세션 시간 기준은 첫 유효 PyAV 패킷 또는 스트림의 time_base다. 이후 패킷의 pts는 세션 기준으로 환산하여 디코더에 제출하고 실제 출력 API에서 되받는다. 미정 시각은 int64 최솟값을 내부 표식으로 사용하고 외부에는 None으로 내보낸다.
