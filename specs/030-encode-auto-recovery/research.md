# 조사: 인코더 자동 복구

## 예외 경계와 재시도

결정: 디코더와 동일하게 RuntimeError와 설치된 PyNvVCException을 네이티브 호출 경계에서만 복구한다. 지원 불가 예외는 전파한다. 실패 후 1초 동안 입력을 소비하여 버리고 다음 새 프레임에서 재시도한다.
근거: 설치된 라이브러리의 예외는 RuntimeError와 별도 클래스다. 생산자 전체 Exception 포착은 입력 오류와 프로그래밍 결함을 숨긴다. 매 프레임 생성 재시도는 NVENC 세션과 로그를 과도하게 사용한다.
대안: 전체 파이프라인 재시작과 실패 프레임 재처리는 제외했다.

## 헤더와 시간 축

결정: h264/hevc에 repeatspspps=1을 적용하고 새 세션의 첫 출력을 실제로 독립 디코딩한다. process 시작의 FPS, time_base 및 next_pts를 공유한다.
근거: 같은 형식의 재생성에서는 RTSPPublish가 연결을 유지하므로 인밴드 시작 프레임과 헤더가 필요하다. next_pts만 유지한 채 time_base를 바꾸면 시각이 역행할 수 있다.
참고: [NVIDIA 인코딩 설정과 종료 안내](https://docs.nvidia.com/video-technologies/pynvvideocodec/pynvc-api-prog-guide/using_pynvvideocodec_apis.html). repeatspspps는 IDR마다 SPS/PPS를 기록하는 옵션이다.

## 자원 수명

결정: 실패 인코더에 종료 호출을 재시도하지 않는다. 프레임 처리 실패 시 스트림 작업 완료 후 해제하고, 정상 변경 시 이전 메타데이터로 잔여 패킷을 출력한다. generator 종료나 소스 오류에도 finally에서 인코더를 먼저 해제한다.
근거: speckit-plan 연구 단계의 읽기 전용 검토에서 CUDA 범위 예외 분리, 외부 프레임 보존, 이전 메타데이터 출력 및 스트림 수명 순서를 확인했다.
대안: 실패한 인코더의 지연 출력을 복구 세션과 섞는 방식은 제외했다.
