# 자료 모델: NVIDIA 인코딩

## 입력 프레임 컨텍스트

- `frame`: NVIDIA 인코더에 전달할 디코딩 프레임.
- `video_stream`: 코덱과 크기를 읽고 출력 컨텍스트에 보존할 비디오 스트림.
- `cuda_stream`: 인코더 생성과 프레임 인코딩에 사용할 CUDA 스트림.
- `pixel_format`: 인코더 입력 픽셀 형식.

이 네 속성의 생성 규칙은 [NVIDIA 디코딩 자료 모델](../006-nvidia-decode/data-model.md)에 있다.

## 인코더 결과 항목

바이트열이나 압축 데이터를 담은 사전·목록으로 표현된다. 사전의 `bitstream`, `data`, `packet`, `encoded_data`, `payload` 키를 우선 확인하고 중첩된 값에서 압축 바이트를 찾는다. 빈 압축 바이트는 출력하지 않는다.

## 출력 패킷 컨텍스트

- `packet`: 압축 바이트를 담은 `av.Packet`. `pts`, `dts`, `time_base`, `duration`이 설정된다.
- `video_stream`: 입력 프레임 컨텍스트에서 받은 비디오 스트림.

시간 기준은 `1 / fps`이고 생성된 패킷마다 PTS와 DTS가 1씩 증가한다. 이 계약의 소비자는 [RTSP 송출 단계](../004-rtsp-publish/data-model.md)다.
