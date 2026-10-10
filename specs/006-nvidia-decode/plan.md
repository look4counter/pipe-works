# 구현 계획: 최신 프레임 디코딩

## 압축 패킷 직접 전달

`src/pipeworks/embedded/nvidia_decode.py`에서 `packet.buffer_ptr`와 `packet.size`를 PacketData의 bsl_data와 bsl에 연결한다. 입력 컨텍스트는 decode 호출 반환까지 보관하고 이후 해제한다. ctypes import와 중간 버퍼를 제거한다. 공개 인터페이스와 의존성 변경은 없다. `tests/test_nvidia_decode.py`의 모의 패킷에 주소·크기 계약을 제공하고 원본 주소·길이·바이트 변환 금지를 검증한다. 보고서·핫스왑 모의 패킷도 갱신한다. 실제 GPU 디코더와 RTSPSource·RTSPPublish 회귀를 확인한다. 미작성 헌장 템플릿 외 추가 원칙은 없으며 한글 문서와 speckit 절차를 따른다.

**명세**: [spec.md](spec.md) | **날짜**: 2026-10-09

## 요약

NvidiaDecode 내부 생산 스레드와 Condition 기반 30개 FIFO 큐을 유지한다. 생산자는 GetNumDecodedFrame과 GetLockedFrame으로 디코더 소유 버퍼를 빌리고, CUDA Array Interface를 통해 같은 주소를 사용하는 PyTorch 텐서를 게시한다. 소비자는 별도 CUDA 스트림에서 준비 이벤트를 기다린다. 버퍼의 마지막 텐서 참조와 GPU 사용 완료를 확인한 뒤 UnlockFrame으로 반환한다.

## 기술 배경

Python 3.11, PyTorch CUDA, PyNvVideoCodec 2.2.2와 기존 Step·ContextVar 통계를 사용한다. 새로운 의존성은 없다. 로컬 DLL 검색 경로를 명시한 검증 프로세스에서 실제 NVDEC/NVENC 실행을 확인했다. 일반 실행의 DLL 설정은 기존 환경 설정을 따른다.

## 원칙 점검

헌법은 미작성 템플릿이다. AGENTS.md의 한글 문서와 speckit 순서를 따른다. 작업자 오류, 취소, GPU 수명과 제한된 버퍼를 함께 검증한다. 설계 후에도 위반은 없다.

## 구조와 구현 지점

- `src/pipeworks/embedded/nvidia_decode.py`: 생산자 스레드, 최신 대기 슬롯, 독립된 디코딩·소비 스트림, 잠금 버퍼와 완료 이벤트·지연 반환, EOF·오류·취소 정리.
- `src/pipeworks/execution.py`, `src/pipeworks/embedded/rtsp_source.py`: 생산자에 한정된 수신 취소 맥락. 이미 실행 중인 읽기는 기존 timeout_ms로 반환한다. 재연결 대기는 취소로 깨운다.
- `src/pipeworks/hotswap.py`: 오류 복구를 사용하지 않는 내장 단계는 입력 복구 목록을 보관하지 않는다. 취소 시 생산자가 입력 구간을 닫을 수 있게 한다.
- `tests/test_nvidia_decode.py`: 최신 정책, 처리 중 프레임 불변성, 생산자 진행, EOF·Flush·오류·취소·통계·핫스왑 검증.
- `tests/test_report.py`, `tests/test_hotswap.py`: 기존 디코더 모의 계약 유지.
- `docs/pipeworks/embedded/nvidia_decode.md`, `README.md`: 최신 기본 동작, 무복사 공유, 폐기 통계와 제한 안내.

## 수명과 종료 설계

실제 Decode/GetFrame 출력의 DLPack 참조는 풀 재사용을 막지 않으므로 사용하지 않는다. GetNumDecodedFrame(packet) 후 각 출력에 GetLockedFrame()을 호출한다. 반환 주소와 GetWidth/GetHeight/GetFrameSize/픽셀 형식으로 공유 뷰를 만들고 공개 torch.as_tensor의 CUDA Array Interface 경로로 텐서를 가져온다. PyTorch는 뷰 객체를 보관하며 DLPack 재공유도 동일 저장소 수명을 유지한다. 뷰는 디코더와 잠금 주소를 소유한다.

생산 스트림 준비 이벤트를 기록하고 소비 스트림은 wait_event로 연결한다. yield 반환 시 소비 스트림 완료 이벤트를 기록하며 CPU stream.synchronize는 제거한다. 마지막 텐서·컨텍스트 참조가 해제되면 뷰가 반환을 예약하고, 생산자가 이벤트 query 후 UnlockFrame을 실행한다. CudaAsync가 보관한 공유 텐서가 남아 있으면 반환을 예약하지 않는다. 소비 중단이나 슬롯 교체에서도 준비·완료 이벤트 전에 반환하지 않는다.

잠근 출력 버퍼는 최대 34개로 제한한다. 대기 큐 30개와 소비·생산·비동기 반환 여유 4개를 포함한다. 소비 중, 최신 대기, 비동기 소비자가 보관한 프레임과 반환 대기를 포함한다. 상한 도달 시 완료 이벤트 또는 참조 반환을 기다려 무제한 잠금 버퍼 증가를 막는다. 프레임을 외부에 계속 보관하는 호출자는 이를 해제해야 생산이 재개된다. 네이티브 디코더 내부 참조·재정렬 버퍼는 별도다. 정상 경로는 생산자만 UnlockFrame을 실행하고, 생산자 종료 후 남은 외부 참조 해제는 잠금으로 직렬화한 종료 경로에서 안전하게 반환한다.

실제 2.2.2에는 Flush가 없으므로 길이 0인 PacketData를 GetNumDecodedFrame에 전달해 EOF를 처리한다. 기존 불투명 모의 디코더의 Decode/Flush 경로는 회귀 검증 호환용으로 유지하되 실제 GPU 프레임에는 잠금 API를 요구한다. 픽셀 형식별 크기와 스트라이드를 확인해 검증되지 않은 레이아웃을 임의로 추정하지 않는다.

copy_context로 수신 통계를 유지한다. 오류 또는 EOF는 Condition을 깨운다. 오류는 대기 프레임보다 우선 전달한다. 정상 EOF에서는 남은 큐를 FIFO 순서로 모두 전달한다. 취소는 생산자 소유 입력에 전달하고 생산자 종료를 기다린 뒤 반환한다. 입력 반복자를 다른 스레드에서 강제로 닫지 않는다. RTSP 읽기 중 취소는 기존 읽기 제한 시간 내에 반영된다.

## 검증

### 다단계 비동기 정체 보완

문서는 `docs/pipeworks/embedded/async.md`, 디코더 문서와 quickstart에 완료 요청의 수명 계약 및 조합 검증을 반영한다.

실제 디코더와 세 단계 CudaAsync 및 Tap 조합에서 잠금 4개·반환 대기 0개로 생산이 멈추는 문제를 재현했다. 이전 성공 결과의 임시 속성 사전과 버린 입력의 지역 참조를 다음 입력 요청 전에 해제한다. 완료된 요청의 내부 작업 컨텍스트와 입력 텐서 보관도 해제한다. 정상 결과는 별도 결과 컨텍스트로 전달한 뒤 내부 원본 참조를 정리하며, 타임아웃 작업은 GPU 작업이 끝난 뒤 정리한다. 사용 중인 외부 출력·DLPack 별칭은 유지한다. `src/pipeworks/embedded/cuda_async.py`, `tests/test_async.py`, `tests/test_nvidia_decode.py`가 추가 구현 지점이다. 잠금 상한을 늘리는 방식으로 문제를 숨기지 않는다.

이벤트로 생산자·소비자의 실행 순서를 제어하여 최신 프레임 교체를 결정적으로 검증한다. 실제 NVDEC가 후속 프레임을 생성해도 잠금 버퍼 내용과 주소가 유지되고 NVENC가 공유 텐서를 소비하는지 확인한다. 미완료 반환 이벤트, 마지막 텐서 참조, 잠금 상한, 오류·취소·EOF를 검증한다. 통계와 복구 목록 및 비동기·감지·인코딩·RTSP 회귀 검사를 실행한 뒤 수렴을 확인한다.
# 실제 예제의 반복자 참조 정리

2026-10-10 범위: FR-013과 SC-008에 따라 `src/pipeworks/hotswap.py`, `src/pipeworks/embedded/tap.py`, `examples/step/box_overlay.py`의 이미 사용한 출력 참조를 정리한다. 사용 중인 Tap 입력과 외부 텐서는 계속 보호하며 잠금 상한 4개와 무복사 정책은 유지한다. 실제 예제 실행 경로와 네트워크 없는 실제 디코더 회귀를 모두 검증한다. 기존 계획의 헌법 점검 결과를 유지하며 추가 의존성과 외부 송출은 없다.

## 30개 큐 확대 설계

`deque`로 최대 30개 대기 프레임을 관리한다. 새 버퍼 획득 전에 큐가 가득 차면 가장 오래된 대기 컨텍스트를 제거하고 폐기 건수를 증가시킨다. 디코딩 결과를 모두 순서대로 게시하고 취소 시 큐 전체를 해제한다. 잠금 상한은 34개다. 앞선 4개 상한 설명은 이전 수정의 역사이며 이번 정책이 대체한다.

## 연속 추론의 출력 할당기 누적 수정

실제 엔진 40회 추론 후 할당기 40개가 생존하고 할당 메모리가 112MiB로 증가했다. 세션 종료 후에야 반환됐다. `src/pipeworks/embedded/tensor_rt_inference.py`에서 출력 바인딩별 할당기 하나만 등록한다. 매 추론마다 동일 할당기의 형상·오류·버퍼 상태를 초기화하고 새 출력 버퍼를 준비하여 기존 출력 텐서를 덮어쓰지 않는다. 동적 형상·정렬·빈 출력 계약도 유지한다. 큐 30개와 잠금 상한 34개는 유지한다.
