# 비디오 메타데이터 계약

video_stream은 av.VideoStream이 아닌 불변 VideoStreamInfo다. codec_context.name·width·height·extradata, codec.name, width·height, time_base, average_rate, index, connection_id를 제공한다. 원본 컨테이너·코덱 객체는 포함하지 않는다.
사용자 정의 소스는 VideoStreamInfo.from_stream을 컨테이너가 열린 동안 한 번 호출한다. 사용자 정의 단계는 같은 연결의 값을 공유한다. 기존 av.VideoStream 전용 메서드와 변경 연산은 지원하지 않는다.
송출 입력은 packet과 메타데이터다. 송출은 시간 기준 보정·재시도 계약을 유지한다. 재인코딩은 입력이 아닌 출력 헤더와 시간 기준의 새 메타데이터를 전달한다.

CodecInfo는 빈 코덱 이름과 0 이하 너비·높이를 생성 시 검증 예외 없이 보존한다. 이는 후속 디코딩·인코딩 성공을 보장하지 않는다. extradata 복사와 불변성은 유지한다.

RTSPSource는 연결당 메타정보를 확인하고 비정상 연결의 패킷을 전달하지 않는다. 비디오 스트림·코덱 부재, 빈 이름, 비정상 크기와 복사·변환 실패 등은 경고와 수신 실패로 기록하며 연결을 닫은 후 reconnect_interval_ms를 기다려 다시 연다. 이 복구는 reconnect=False에도 적용된다. 정상적인 이름을 특정 GPU 코덱 목록으로 제한하지 않으며 선택 시간 값의 부재는 허용한다. 일반 연결·수신 오류의 reconnect 정책과 종료·취소 계약은 유지한다.
