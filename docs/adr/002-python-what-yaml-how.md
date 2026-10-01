# ADR-002: Python은 What을, YAML은 How를 표현한다

## 상태

채택

## 배경

Python 코드에서는 Pipeline의 의미와 정체성을 드러내고, 운영 환경에 따른
튜닝은 코드 밖에서 변경할 수 있어야 한다.

## 결정

생성자 인자는 RTSP URL, 모델 경로, Action 대상, 출력 대상, stream ID,
stage 이름처럼 연결할 대상을 담는다. YAML은 timeout, retry, reconnect,
confidence, device, FP16, codec, bitrate, queue size, drop policy,
batch wait처럼 동작 방식을 조정한다.

## 검토한 대안

- 모든 것을 YAML에 넣기: 배포에는 유리하지만 Python Pipeline이 불투명해진다.
- 모든 것을 Python에 넣기: 읽기는 쉽지만 운영 튜닝마다 코드를 바꾸게 된다.

## 결과

설정 병합 계층이 필요하다. 알 수 없는 설정은 관찰 가능하게 기록하되,
MVP 실행 자체를 막지는 않는다.
