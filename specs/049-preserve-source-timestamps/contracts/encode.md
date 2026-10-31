# 공개 계약

`NvidiaEncode(*, gpu_id=0, fps=30, preserve_timestamps=False)`를 제공한다. 동일 YAML 키가 생성자 값을 덮어쓰며 제거하면 생성자 값으로 돌아간다. 옵션은 불리언이어야 한다.

True이면 컨텍스트 pts·time_base·선택적 duration을 보존한다. DTS는 PTS와 같다. time_base 생략 시 video_stream.time_base를 사용한다. 원본이 없거나 유효하지 않으면 경고와 함께 폐기한다. fps는 네이티브 인코더 설정에 계속 사용한다.

False는 기존 연속 PTS/DTS와 duration=1, time_base=1/fps를 유지한다. RTSPPublish는 중복·역행 DTS 패킷을 폐기하고 PTS/DTS를 증가시키지 않는다. 실제 시각은 time_base를 반영하여 비교하며 DTS 누락 보완은 유지한다.

수정 wheel의 버전은 2.2.2+pipeworks.1이다. PyNvDecoder.GetLockedFrameWithPTS()는 (포인터, 부호 있는 PTS)를 반환하고 기존 UnlockFrame(포인터)으로 해제한다. 출력이 없으면 예외다. NvidiaDecode는 이 API가 제공하는 PTS와 PyAV에서 선택한 시간 기준을 출력 컨텍스트에 전달한다. 공식 wheel에서는 pts=None을 전달하여 인코더 기본 모드를 계속 지원한다.
