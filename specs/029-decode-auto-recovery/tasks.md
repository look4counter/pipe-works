# 작업 목록: 디코더 자동 복구

**입력**: [명세](spec.md), [계획](plan.md), [조사](research.md)

## 1단계: 준비

- [X] T001 .gitignore의 Python 제외 규칙과 tests/test_nvidia_decode.py 실행 환경을 확인한다.

## 2단계: 기반

- [X] T002 tests/test_nvidia_decode.py의 입력 fixture가 연속 패킷에 동일 스트림을 사용하도록 하고 자동 복구 시험을 먼저 작성하여 실패를 확인한다. FR-001~006.

## 3단계: 사용자 이야기 1 — 오류 후 자동 재개

**독립 검증**: 오류와 비키프레임 이후 정상 키프레임 출력, 연속 생성 실패, 마지막 flush 오류를 검증한다.

- [X] T003 [US1] src/pipeworks/embedded/nvidia_decode.py에 네이티브 호출 예외 경계와 키프레임 기반 재생성 및 복구 기록을 구현한다. FR-001, FR-002, FR-005, FR-006.

## 4단계: 사용자 이야기 2 — 재연결 및 수명

**독립 검증**: 새 스트림 감지, 이전 프레임 참조 유지, 대기 중 취소, 소스 오류 전파를 검증한다.

- [X] T004 [US2] src/pipeworks/embedded/nvidia_decode.py에 큐 초기화와 이전 풀 정리 및 스트림 교체 처리를 구현한다. FR-003, FR-004, FR-005.
- [X] T005 [US2] tests/test_nvidia_decode.py에 실제 GPU 복구 중 이전 Tensor/DLPack 잠금 수명 및 소비자 스트림 재사용 시험을 추가하고 검증한다. FR-003, SC-002.

## 5단계: 검증 및 문서

- [X] T006 docs/pipeworks/embedded/nvidia_decode.md 및 docs/reference/NvidiaDecode.html의 기존 디코더 참조 문서에 자동 복구 동작과 한계를 갱신한다. FR-006.
- [X] T007 specs/029-decode-auto-recovery/quickstart.md에 따라 디코더 및 관련 회귀 시험과 정적 검사를 수행한다. SC-001~004.

## 의존성과 실행 순서

T001 → T002 → T003 → T004 → T005 → T006 → T007 순서로 진행한다. 같은 파일을 수정하는 작업이므로 병렬 변경은 하지 않는다. 문서 확인과 읽기 전용 연구는 독립 수행할 수 있다.

## 구현 전략

먼저 오류 이후 영상 재개를 구현하고 스트림 교체와 자원 수명을 검증한 다음 운영 문서를 갱신한다. 모든 구현 이후 speckit-converge로 요구사항과 코드의 차이를 확인한다.
