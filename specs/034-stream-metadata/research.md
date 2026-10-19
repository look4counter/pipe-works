# 연구 결과

## 결정: 불변 값 모델

연결당 frozen dataclass를 생성한다. codec_context와 codec 접근은 독립적인 CodecInfo 값을 반환한다. 연결 ID는 무작위 문자열로 연결과 프로세스 사이 충돌을 피한다. 원본 객체 유지와 deepcopy 방식은 닫힌 네이티브 리소스 수명을 해결하지 못해 제외한다.

## 결정: 출력 스트림 복원

설치된 PyAV 18.1.0 av/container/output.py 확인 결과 add_mux_stream에는 extradata 설정 경로가 없다. 일반 add_stream은 start_encoding에서 인코더를 열어 헤더를 변경한다. 로컬 임시 출력으로 add_stream_from_template 초기화를 수행한 뒤 출력 codec_context에 독립 값들을 넣으면 자동 인코더 열기를 피하고 복사한 extradata를 보존한다. 실제 파일 회귀 검증으로 확인한다.

## 결정: 재인코딩 헤더

공식 NVIDIA 인코더 API에 GetSequenceParams는 없다. 현재 repeatspspps=1 설정을 유지하고 최초 출력 Annex B NAL에서 h264 SPS/PPS 또는 hevc VPS/SPS/PPS를 추출한다. 원본 입력 헤더는 출력에 재사용하지 않는다.

참고: https://docs.nvidia.com/video-technologies/pynvvideocodec/pynvc-api-reference/encoder.html
초기 단독 가져오기는 DLL 로드 실패였으나 기존 테스트의 DLL 경로 설정으로 실제 GPU 검증이 가능했다. h264·hevc 인코더 복구와 출력 메타데이터를 이용한 파일 송출·재디코딩 검증을 통과했다.

## 2026-10-20 추가 결정

- 결정: 생성 시 이름·크기 검증 예외만 제거한다.
- 근거: 사용자가 해당 ValueError 제거를 명시했다.
- 대안: 값 보정과 재연결 정책 추가는 요청 범위 밖이므로 적용하지 않는다.

## RTSP 메타정보 복구 결정

- 결정: 잘못된 메타정보를 RTSPSource에서 검출해 컨테이너를 재생성하고 기존 대기·취소 경로를 사용한다.
- 근거: 후속 예제 단계에서 입력 생성기의 종료를 복구할 수 없으므로 연결 소유자가 처리해야 한다. 원본 타입 검사로 None이 문자열로 변환되거나 소수 크기가 잘리는 것을 방지한다.
- 대안: CodecInfo의 생성 거부 복원, 모든 예외 재시도, GPU 지원 코덱만 허용, 프레임마다 복사는 기존 계약과 범위를 바꾸므로 제외한다.
