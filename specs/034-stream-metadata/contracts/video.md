# 비디오 메타데이터 계약

video_stream은 av.VideoStream이 아닌 불변 VideoStreamInfo다. codec_context.name·width·height·extradata, codec.name, width·height, time_base, average_rate, index, connection_id를 제공한다. 원본 컨테이너·코덱 객체는 포함하지 않는다.
사용자 정의 소스는 VideoStreamInfo.from_stream을 컨테이너가 열린 동안 한 번 호출한다. 사용자 정의 단계는 같은 연결의 값을 공유한다. 기존 av.VideoStream 전용 메서드와 변경 연산은 지원하지 않는다.
송출 입력은 packet과 메타데이터다. 송출은 시간 기준 보정·재시도 계약을 유지한다. 재인코딩은 입력이 아닌 출력 헤더와 시간 기준의 새 메타데이터를 전달한다.
