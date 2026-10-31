# 설계 조사

- 결정: 컨텍스트 pts와 time_base를 사용하며 누락 시 폐기한다. 현재 디코더는 잠금 포인터만 얻으므로 시각을 출력하지 않는다. 압축 패킷 시각을 현재 출력에 붙이는 대안은 재정렬·지연에서 대응이 틀려 제외했다.
- 결정: FIFO 시각 큐를 사용한다. B프레임이 없어도 출력 지연이 가능하다.
- 결정: DTS는 PTS와 같다. 재인코딩한 영상에 원본 압축 패킷의 DTS를 재사용하지 않는다.
- 소스 확인: 2.2.2의 Python GetLockedFrame 바인딩은 C++ 호출의 pTimestamp에 NULL을 전달한다. 내부 GetLockedFrame은 포인터와 PTS를 동일 잠금 구간에서 반환한다. 따라서 새 Python 메서드만 추가하면 된다. GetFrame의 설명은 잠금을 언급하지만 구현은 비잠금 API를 호출하여 사용하지 않는다.
- 빌드 결정: 원본 ZIP을 고정 해시로 검증하고 최소 패치와 별도 로컬 버전 wheel을 생성한다. 기존 공식 설치를 자동으로 교체하지 않는다. 빌드 시 네트워크가 없는 환경에서는 개발 의존성을 미리 준비하고 CMake 외부 의존성 경로를 전달할 수 있어야 한다.
- 근거: [NVIDIA 공식 API](https://docs.nvidia.com/video-technologies/pynvvideocodec/pynvc-api-reference/decoder.html)는 DecodedFrame의 timestamp·getPTS를 설명하지만 GetLockedFrame은 포인터를 반환한다고 명시한다. 이번 변경은 버퍼 수명 계약을 유지한다.
