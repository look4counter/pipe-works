# 데이터 모델

- CodecInfo: name(str), width(int), height(int), extradata(bytes), pix_fmt(str 또는 없음). 불변이며 네이티브 참조를 포함하지 않는다.
- VideoStreamInfo: codec_context(CodecInfo), time_base(Fraction 또는 없음), average_rate(Fraction 또는 없음), index(int), connection_id(str). codec·width·height 편의 접근을 제공한다.
- 수신 연결: 열린 원본 스트림 → 메타데이터 1회 생성 → 패킷·프레임 공유 → 컨테이너 닫힘 이후에도 값 유효.
- 인코더 세대: 최초 패킷 → 실제 출력 헤더와 시간 기준으로 새 메타데이터 → 같은 세대 모든 패킷 공유 → 교체 전 flush도 이전 세대 값 사용.
