# 조사 및 구현 결정: 미디어 파이프라인

- **Processing paths**: CLI and web form accept `nvidia` and `bypass`. NVIDIA defaults to GPU 0 and has no CPU fallback.
- **입력**: PyAV가 RTSP 입력의 첫 비디오 스트림을 demux한다. 연결·읽기 timeout은 각각 5초이며 오류 또는 EOF 뒤 3초 후 재시도한다.
- **NVIDIA 디코드**: PyAV 패킷을 PyNvVideoCodec `PacketData`로 감싸고 NVDEC에서 프레임을 만든다. 현재 PacketData에는 비트스트림과 크기만 설정한다.
- **NVIDIA 인코드 및 출력**: 프레임은 NVENC으로 새로 압축하고, 압축 바이트를 PyAV RTSP muxer로 전달한다. 입력 packet의 timestamp·keyframe·extradata를 유지하지 않으며 PTS/DTS는 출력 packet 순번에서 생성한다. DB 설정을 읽는 NVIDIA/RTSP 종단 간 smoke test와 mux 설정 단위 테스트가 통과했다.
- **단계 모듈**: 활성 Python 파일은 동적 import하며 수정 시간을 1초 간격으로 polling한다. metadata는 `metadata()` 반환값, inference/postprocess는 모듈 객체를 교체한다.
- **Frame callbacks**: pytorch inference calls `on_frame(infer, parameters, frame)` for every frame; postprocess calls `on_frame(parameters, frame)`. `infer` is true for interval frames. Callback errors are recorded and the input frame advances to the next stage. Failed reloads retain the previous module; metadata startup failures are tolerated and retried by the watcher.
- **미완성 계약**: FRAME TYPE은 pytorch만 지원한다. inference interval은 첫 프레임부터 지정 간격으로 적용하며 활성 metadata는 `FrameContext.metadata`를 통해 프레임 콜백에 전달한다.
- **검증**: 파서·DB·Supervisor의 일부 단위 테스트는 있지만 GPU/RTSP 입출력 경로는 통합 환경에서 별도 확인이 필요하다.


## Bypass pipe type

The bypass path uses PyAV stream templates and remuxes compressed video packets without decoding or re-encoding. Metadata, inference, and postprocess are automatically disabled. RTP datagrams are not copied byte-for-byte.
