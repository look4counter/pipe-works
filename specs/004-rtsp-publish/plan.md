# 구현 계획: RTSP 패킷 송출

**명세**: [기능 명세](spec.md)

## 기술 배경

- `PipelineContext`는 고정 필드가 없다. RTSP 소스와 인코딩 단계는 `packet`, `video_stream` 필드를 사용한다.
- `RTSPPublish.process()`는 입력 반복자를 소비하고 종료 시 출력 연결을 닫는다.
- 출력에는 PyAV의 패킷과 템플릿으로 사용할 비디오 스트림이 필요하다.

## 설계

1. 입력마다 `packet`과 `video_stream`을 검증한다.
2. 입력 스트림의 코덱·크기·추가 데이터·시간 기준으로 변경을 감지하고 출력 스트림을 템플릿에서 만든다.
3. 패킷 시간 기준을 확인하고 누락·역행 DTS를 보정한 뒤 패킷을 송출한다.
4. 출력 열기나 송출 실패 후 단조 시계 기준 재시도 시점까지 패킷을 건너뛴다. 재연결이 꺼져 있으면 오류를 전달한다.
5. 생성기의 `finally`에서 열린 출력 연결을 닫는다. 닫기 오류는 기록한다.
6. 출력 연결 옵션의 패킷 크기는 문자열로, `timeout_ms`는 밀리초에서 마이크로초로 변환한 문자열로 전달한다.
7. 인코딩 바이트 전용 분기, 새 패킷 생성, FPS 기반 PTS·DTS 생성은 사용하지 않는다.

## 자료 모델과 계약

- [자료 모델](data-model.md)
- 입력 출처가 어느 단계인지에 관계없이 같은 두 필드와 송출 가능한 패킷 객체가 필요하다.
- 인코딩 단계가 이 입력을 어떻게 만드는지는 [NVIDIA 인코딩 계획](../005-nvidia-encode/plan.md)에서 다룬다.

## 영향 파일

- `src/pipeworks/embedded/rtsp_publish.py`
- `tests/test_rtsp_publish.py`

## 검증

- 모의 PyAV 출력으로 패킷 계약, DTS 보정, 스트림 변경, 실패 복구, 옵션 형식, 자원 정리를 확인한다.
- `python -m unittest discover -s tests -p test_rtsp_publish.py`를 실행한다.
- 전체 테스트의 다른 단계 오류는 별도로 확인한다.
