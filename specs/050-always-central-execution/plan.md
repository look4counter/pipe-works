# 구현 계획: 배치 여부와 독립적인 중앙 실행

작성일: 2026-11-06. 명세: [spec.md](spec.md).

## 요약

Pipeline.run()의 배치 검사와 로컬 분기를 제거하고 기존 run_remote를 항상 사용한다. 서버는 기존 _run_local(stop)을 호출하므로 원격 실행이 재귀하지 않는다. 추론 구현은 변경하지 않는다.

## 기술 맥락

Python 3.11.9, Windows, PyTorch, cloudpickle, unittest 기반 라이브러리다. 추가 의존성·저장소·성능 목표 변경은 없다. 영향 범위는 실행 경로, 관련 회귀 검증과 사용자 문서다. 중앙 통합 검증은 Windows Named Pipe 권한에 의존한다.

## 헌장 점검

헌장은 미작성 템플릿이므로 구체 원칙 검사는 생략한다. AGENTS.md의 한국어 문서 및 speckit 전체 절차를 준수한다. 설계 전후 위반은 없다.

## 0단계: 조사

[research.md](research.md)에 실행 분기와 추론 분리 근거를 기록한다. 기술 선택의 미해결 사항은 없다.

## 1단계: 설계

[data-model.md](data-model.md), [실행 계약](contracts/execution.md), [검증 안내](quickstart.md)를 작성한다.

## 파일 구조와 변경점

- src/pipeworks/pipeline.py: 배치 검사 함수와 run의 로컬 분기 제거. _iter_steps는 보고 및 설정 감시에 필요하므로 유지한다.
- tests/test_pipeline_routing.py: batch 참·거짓, 래퍼, 빈 파이프라인, 기본·사용자 별칭, 원격 실패 전달과 서버 실행기의 비재귀성을 검증한다.
- tests/test_central_process.py: 옛 batch_process 표기를 갱신하고 강제 원격 실행용 하위 클래스 우회를 제거한다. 문법 검증을 수행한다.
- tests/test_inference_contract.py: 공유 추론 호출 여부를 확인하여 batch=False가 공유 배치를 사용하지 않음을 검증한다.
- README.md, docs/pipeworks/pipeline.md, main.md, getting_started.md, embedded/yolo_inference.md: 항상 중앙 실행 및 배치 옵션 의미를 안내한다.

## 검증 전략

경로와 별칭 계약 검증, 개별·공유 추론 계약 검증을 실행한다. 별도 서버 별칭으로 실제 중앙 실행을 시도하여 실패 시 환경 제약과 단위 검증 결과를 구분한다. 기존 추론 GPU 회귀를 실행한다.

## 복잡도

새 설정·새 실행기·새 서버 수명 주기를 추가하지 않는다.
