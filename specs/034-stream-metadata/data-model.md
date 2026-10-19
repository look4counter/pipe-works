# 데이터 모델

- CodecInfo: name(str), width(int), height(int), extradata(bytes), pix_fmt(str 또는 없음). 불변이며 네이티브 참조를 포함하지 않는다.
- VideoStreamInfo: codec_context(CodecInfo), time_base(Fraction 또는 없음), average_rate(Fraction 또는 없음), index(int), connection_id(str). codec·width·height 편의 접근을 제공한다.
- 수신 연결: 열린 원본 스트림 → 메타데이터 1회 생성 → 패킷·프레임 공유 → 컨테이너 닫힘 이후에도 값 유효.
- 인코더 세대: 최초 패킷 → 실제 출력 헤더와 시간 기준으로 새 메타데이터 → 같은 세대 모든 패킷 공유 → 교체 전 flush도 이전 세대 값 사용.

빈 코덱 이름과 0 이하 크기도 생성 시 거부하지 않고 원래 값으로 보존한다. extradata 독립 복사와 불변성은 유지한다.

RTSP 연결은 열기 → 메타정보 확인 → 정상 패킷 전달 또는 비정상 연결 닫기 → 취소 가능한 대기 → 새 연결 열기 순서다. 비디오 스트림 부재, 잘못된 이름·크기, 복사 실패, 비양수 시간 값과 음수 인덱스는 비정상이다. 선택 시간 값은 없어도 된다. 검증은 연결당 한 번이며 불변 값 모델 자체의 생성 계약은 바꾸지 않는다.
