# 조사: 디코더 자동 복구

## 예외 경계

결정: 네이티브 메서드에서만 RuntimeError와 PyNvVCException을 복구한다. 지원 불가 예외는 전파한다.
근거: 설치된 2.2.2의 PyNvVCException은 RuntimeError가 아닌 Exception 직계 하위이며, PyNvVCExceptionUnsupported도 별도 클래스다. 실제 Python import로 확인했다.
대안: 생산자 전체 Exception 포착은 설정 및 소스 오류를 숨기므로 제외했다.
참고: [NVIDIA 오류 처리 안내](https://docs.nvidia.com/video-technologies/pynvvideocodec/pynvc-api-prog-guide/using_pynvvideocodec_apis.html).

## 재동기화

결정: 오류 후 다음 키프레임에서 디코더를 생성한다. 생성 실패에도 다음 키프레임에서 재시도한다.
근거: 참조 프레임을 잃은 디코더에 비키프레임을 계속 넣는 일을 피하고 재시도 빈도를 입력 주기로 제한한다.
대안: 모든 패킷 재시도는 손상 입력에서 반복 생성과 로그를 유발한다. 전체 파이프라인 재시작은 기존 후속 처리 상태를 잃는다.

## 자원 수명

결정: 큐를 비우고 기존 풀을 close하되 외부 owner가 풀과 디코더를 계속 보유한다. 소비자 스트림은 유지한다.
근거: close는 이미 반환된 버퍼를 정리하며 외부 잠금은 마지막 소유자 해제까지 보존한다. 계획 단계의 읽기 전용 독립 검토에서도 이 방식과 테스트 스트림 fixture 수정 필요성을 확인했다.
대안: 모든 버퍼 강제 해제는 처리 중인 프레임을 손상시킬 수 있다.
