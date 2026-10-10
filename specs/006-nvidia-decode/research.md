# 설계 검토: NVIDIA 비디오 디코딩

## 압축 패킷 복사 제거 조사

결정: PyAV buffer_ptr와 size를 PacketData에 직접 연결하고 호출 반환까지 원본을 보관한다. 설치된 PyAV에서 주소·크기 제공을 확인했다. [NVIDIA 가이드](https://docs.nvidia.com/video-technologies/pynvvideocodec/pdf/PyNvVideoCodec_API_ProgGuide.pdf)는 bsl_data를 비트스트림 포인터로 정의하고 [NVDEC 가이드](https://docs.nvidia.com/video-technologies/video-codec-sdk/13.0/nvdec-video-decoder-api-prog-guide/index.html)는 파서 콜백의 동기 실행을 설명한다. PyNvVideoCodec 문서에서 반환 이후 포인터 보관을 명시적으로 금지하는 문장은 찾지 못했으나, 기존 ctypes 버퍼도 호출 반환 직후 해제하므로 입력 소유자의 보관 구간은 동일하다. 실제 GPU 디코딩 회귀로 검증한다. 두 번의 복사 유지와 중간 복사 한 번만 제거하는 대안은 원본 주소가 이미 제공되므로 선택하지 않는다.

- **코덱 선택**: H.264와 H.265/HEVC 코덱 이름을 NVIDIA 디코더 값으로 대응시킨다.
- **패킷 전달**: 패킷 바이트를 버퍼로 만들고 주소와 길이를 전달한다. PTS가 없는 패킷은 PTS를 별도로 설정하지 않는다.
- **출력 단위**: 디코더는 입력 패킷 하나에서 프레임 0개 또는 여러 개를 반환할 수 있다. 최신 사용자 요청에 따라 대기 큐는 최대 30개이며 FIFO로 소비하고 초과 시 가장 오래된 대기 프레임을 버린다. 한 패킷에서 나온 여러 출력도 모두 순서대로 게시한다.
- **종료 처리**: 실제 2.2.2에서는 빈 PacketData로 지연 프레임을 회수한다. 불투명 모의 디코더의 Flush 결과에도 최신 정책을 적용한다.
- **현행 한계**: 네트워크 재연결 자체는 핫스왑 입력 구간을 끝내지 않으므로 디코더를 다시 만들지 않는다. 새 연결의 디코더 상태 처리는 별도 개선이 필요하다.

현재 GPU 수명·잠금·무복사 결정과 공식 문서 및 실제 장비 검증 근거는 [무복사 조사](research-zero-copy.md)에 있다. [최신 프레임 조사](research-latest.md)는 최초 복사 구현의 기록이다.
