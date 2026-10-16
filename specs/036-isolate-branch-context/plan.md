# 구현 계획: 분기 컨텍스트 분리

## 개요 및 기술 맥락

Python 3.11.9의 기존 PipelineContext·스레드·Condition을 유지하고 의존성을 추가하지 않는다.
TapSkipIfBusy의 _InputSlot.offer가 입력을 수락할 때 PipelineContext의 최상위 속성 사전을 복사해 별도 컨텍스트로 보관한다.

## 헌법 검토

헌법은 미작성 템플릿이므로 규범 검사를 생략한다. AGENTS.md의 한글 문서와 전체 speckit 절차를 준수한다. 설계 후에도 위반은 없다.

## 설계

- src/pipeworks/embedded/tap_skip_if_busy.py: 잠금 안에서 closed·busy를 확인한 뒤에만 PipelineContext(**vars(item))을 생성한다. 주 경로는 기존 item을 전달한다.
- 기존 _pipeworks_hotswap_epoch 튜플은 분기 시점 값을 보존한다. 이후 Hotswap의 setattr과 복구 시 속성 사전 복원은 각 컨텍스트에만 적용된다.
- 중첩 사전·영상·CUDA 스트림·불변 영상 메타데이터·_decode_buffer는 동일 객체 참조를 유지한다. 깊은 복사와 영상 clone을 추가하지 않는다.
- 입력 수락·유휴 전환·정상 및 조기 종료의 기존 로직은 유지한다. CudaAsync와 EveryNFrames의 순차 결과 병합은 변경하지 않는다.
- tests/test_tap_skip_if_busy.py에 분기 양방향 속성 격리, 실제 파일 핫스왑, 공통 상류 epoch 보존, 무복사 및 생략·종료 검증을 추가한다.
- docs/pipeworks/embedded/tap_skip_if_busy.md, docs/pipeworks/hotswap.md, README.md에 변경 계약을 반영한다.

## 검증

슬롯 경계의 실제 Hotswap 코드 교체로 주 경로 누적 1, 3을 검증한다. 실제 배경 스레드 실행에서 컨텍스트 격리와 버퍼 참조 동일성을 확인한다. 기존 핫스왑·비동기·프레임 수명·중앙 로그 검증을 실행한다.
