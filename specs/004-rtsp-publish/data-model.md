# 자료 모델: RTSP 송출 입력

## 송출 컨텍스트

- `packet`: 송출할 압축 패킷. `time_base`, `dts`, `pts`, `duration`을 읽고, 보정 과정에서 `time_base`, `dts`, `pts`, `stream`을 수정할 수 있어야 한다.
- `video_stream`: 출력 템플릿으로 사용할 입력 비디오 스트림. `codec_context.name`, `codec_context.extradata`, `width`, `height`, `time_base`를 읽는다. `index`는 선택 속성이다.

두 속성이 모두 있어야 송출할 수 있다. 별도 `data`, `codec`, `width`, `height`, `time_base`, `fps` 조합은 송출 입력이 아니다. 실제 출력에는 PyAV가 받아들일 수 있는 패킷과 스트림 객체가 필요하다.

인코딩 단계의 출력 생성 규칙은 [NVIDIA 인코딩 자료 모델](../005-nvidia-encode/data-model.md)에 둔다.

## 송출 상태

한 번의 `process()` 실행 동안 현재 출력 연결, 출력 스트림, 입력 설정 식별자, 마지막 DTS와 시간 기준, 재시도 가능 시점을 보관한다.
