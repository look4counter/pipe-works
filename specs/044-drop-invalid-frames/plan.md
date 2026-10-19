# 구현 계획: 잘못된 NV12 프레임 폐기

**날짜**: 2026-10-19 | **명세**: [spec.md](spec.md)
**기능 식별자**: 044-drop-invalid-frames. 실제 Git 브랜치는 변경하지 않는다.

## 요약

NV12 크기 오류만 프레임별로 처리한다. 일반 반복자는 다음 입력으로 진행하고, 입력당 출력 하나를 요구하는 래퍼에서는 기존 `_DroppedFrame` 신호를 사용한다.

## 기술 문맥

- Python 3.11.9, PyTorch 2.2.1, CUDA 및 unittest를 사용한다.
- 새로운 의존성, 저장소, 설정 옵션은 추가하지 않는다.
- 수정 대상은 `examples/step/yolo_pre_process.py`, `examples/step/box_overlay.py`, `src/pipeworks/embedded/cuda_async.py`다.
- 검증은 `tests/test_invalid_frame_drop.py`의 동기·비동기·주기 실행 회귀 테스트 및 기존 관련 테스트로 수행한다.
- 기존 피치 처리와 정상 영상 경로를 유지하며 CPU 영상 복사는 추가하지 않는다.

## 헌법 확인

헌법은 미작성 템플릿이므로 적용 가능한 확정 원칙은 없다. 사용자 지침에 따라 모든 신규 Markdown 문서는 한글로 작성하고 speckit 단계를 순서대로 진행한다. 설계 전후 위반 사항은 없다.

## 단계 0: 조사

[research.md](research.md)에 기존 폐기 신호와 반복자 계약 검토를 기록한다. 외부 기술 선택과 미해결 사항은 없다.

## 단계 1: 설계

- 전처리의 NV12 크기 오류를 전용 ValueError 하위 타입으로 구분하고 프레임 반복문에서만 잡는다. 경고와 프로파일 정리 후 다음 입력으로 진행한다.
- 박스 표시의 잘못된 크기는 GPU 작업 전에 폐기한다. 버퍼 크기 검사는 자료형·장치 검사와 분리한다.
- `_can_signal_frame_drop()`가 참이면 폐기 신호를 출력하고, 아니면 출력을 생략한다.
- CudaAsync는 내부 실행에 폐기 범위를 설정하고 `_Stage`가 폐기 신호를 후속 Step에 전달하지 않도록 우회한다. 완료 결과의 폐기 신호는 원본 복사와 실패 시 원본 전달보다 우선한다.
- 디코더 버퍼 정리 시 폐기 신호 타입을 보존한다. 기존 동기화와 소유권 정리는 유지한다.
- 시간 초과 전에 폐기가 완료된 요청은 항상 폐기한다. 이미 시간 초과한 요청의 기존 동작은 유지한다.
- EveryNFrames의 기존 폐기 신호 소비 계약을 재사용한다.

## 프로젝트 구조

기능 문서는 `specs/044-drop-invalid-frames/`에 두고, 소스와 테스트는 위에 지정한 기존 디렉터리를 사용한다. 데이터 규약은 [data-model.md](data-model.md), 호출 규약은 [contracts/frame-drop.md](contracts/frame-drop.md), 검증 절차는 [quickstart.md](quickstart.md)에 기록한다.

## 복잡도 검토

전역 예외 복구를 추가하지 않는다. 기존 폐기 신호를 사용하므로 별도의 프레임 보정이나 재시작 시스템이 필요하지 않다.