# 연구 결과

## 결정: 정리 성공의 즉시 반영과 실패 후 네이티브 재진입 금지

부분 성공 후 retired 전체를 나중에 교체하는 기존 코드는 뒤쪽 반환 실패 시 앞쪽 포인터도 남긴다. 인덱스 기반 즉시 삭제로 해결한다. 실패한 네이티브 반환은 실제 반환 여부가 불명확하므로 자동 재시도하지 않는다. 동기화 실패도 기존 실패 전파를 보존하고 실행별 실패 플래그로 최종 정리 재진입을 막는다.

## 결정: 독립 압축 패킷 복사

계획 단계 연구에서 설치된 PyAV18.1.0 소스와 실제 API를 확인했다. av.Packet(source)는 같은 payload 주소를 별도 AVBufferRef로 감싸며 메타데이터와 side data를 복사하지 않는다. copy.copy·deepcopy는 지원하지 않는다. 직접 수정은 원본 데이터에도 영향을 주어 안전한 공유 복사의 일반 보장이 부족하다.
따라서 av.Packet(source.size)와 update(source)를 사용한다. FFmpeg av_new_packet이 패딩을 포함해 할당하고 압축 데이터를 한 번 복사한다. Python bytes 중간 복사·프레임 또는 GPU 복사는 없다. side data는 iter_sidedata와 set_sidedata(move=True)로 독립 복사한다.

is_keyframe·is_corrupt는 설정 가능하나 is_discard·is_trusted·is_disposable·pos는 읽기 전용이다. 표현 불가 플래그는 무음 손실 대신 명시적 오류로 거부한다. pos는 입력 파일 위치이므로 제외한다. 로컬 실제 H.264 패킷의 병렬 MPEG-TS mux와 원본 불변을 확인했고 실제 RTSP 서버 검증은 수행하지 않았다.
