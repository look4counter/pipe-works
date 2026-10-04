# 자료 모델: RTSP 패킷 컨텍스트

**후속 변경**: 현재 패킷은 별도 하위 클래스 없이 `PipelineContext`에 담으며 종료 이벤트는 사용하지 않는다. [003 자료 모델](../003-step-yaml-config/data-model.md)을 참조한다.

## 패킷 컨텍스트

- 개체: `PipelineContext`
- `video_stream`: 현재 연결에서 선택한 첫 비디오 스트림
- `packet`: 해당 스트림에서 수신한 크기가 있는 원본 패킷
- 생명주기: 한 패킷을 다음 처리 단계로 전달하는 동안 유지

## RTSP 소스

- `url`: 입력 주소
- `transport`: RTSP 전송 방식. 기본값은 `tcp`
- `reconnect`: 재연결 활성 여부. 기본값은 참
- `reconnect_interval`: 재연결 대기 시간. 기본값은 3초
