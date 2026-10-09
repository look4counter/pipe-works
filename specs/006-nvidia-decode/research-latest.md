# 최신 프레임 구현 조사

이 문서는 최초 복사 구현의 조사 기록이다. 현재 설계는 [무복사 조사](research-zero-copy.md)가 대체한다.

- 결정: 디코더 표면과 소비 프레임을 독립 GPU 복사로 분리한다. DLPack은 원본 메모리를 공유하므로 수신 스레드가 계속 진행하는 상황에서 소비 중 프레임을 보장하기 위한 선택이다. 복사 완료 전에 다음 Decode로 넘어가지 않는다.
- 결정: 소비자 스트림을 별도로 만든다. 같은 스트림을 사용하면 뒤쪽 커널·동기화가 디코딩 진행을 막는다.
- 결정: 작업자에 copy_context를 적용한다. RTSPSource의 실행별 수신 통계를 기존 파이프라인 범위에 유지한다.
- 결정: 비복구 내장 Hotswap의 입력 스냅샷 목록을 생성하지 않는다. 백그라운드 입력이 후속 yield 전에 계속 추가되어 숨은 적체가 생길 수 있기 때문이다.
- 결정: 소비자 취소는 맥락의 Event로 RTSP 수신에 전달하며 읽기 자체는 기존 timeout_ms로 종료된다. 실행 중 generator.close를 다른 스레드에서 호출하지 않는다.
- 근거: [NVIDIA DLPack 가이드](https://docs.nvidia.com/video-technologies/pynvvideocodec/pynvc-api-prog-guide/using_pynvvideocodec_apis.html), [인코더 입력 계약](https://docs.nvidia.com/video-technologies/pynvvideocodec/pynvc-api-reference/encoder.html). Encoder는 GPU DLPack 입력을 지원하므로 복사된 torch.Tensor를 직접 전달한다.
- 대안: 디코더 객체를 그대로 보관하는 방식은 surface 수명·재사용에 대한 확실한 계약이 부족하여 선택하지 않았다. 무제한 큐와 압축 패킷 임의 폐기도 선택하지 않았다.
