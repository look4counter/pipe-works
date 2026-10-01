# 품질 게이트

## 현재 적용 게이트

- 승인 기준 게이트: 모든 작업에 측정 가능한 완료 기준이 있어야 한다.
- 단위 테스트 게이트: SDK 핵심 동작은 외부 서비스 없이 결정적으로 검증한다.
- 예제 실행 게이트: 개발자용 예제는 실제로 실행되어야 한다.
- 하네스 게이트: pipeworks --check가 통과해야 한다.

## 기본 검증 명령

    $env:PYTHONPATH='src'; python -m pytest -q
    python -m ruff check src\pipeworks tests\sdk examples
    $env:PYTHONPATH='src'; python -m pipeworks.cli --check

## 확장 예정 게이트

- 정적 품질: ruff, mypy
- 공개 API 계약 테스트
- 실제 제공자/도구 어댑터를 가짜 구현으로 검증하는 통합 테스트
- 실패 의미론: 차단된 작업, 실패한 게이트, 재시도 예산
- 문서 드리프트: 동작 변경 시 스펙과 ADR 갱신

동작 변경은 코드만 수정하고 끝내지 않는다. 관련 예제, 테스트, 스펙,
결정 문서 중 영향을 받는 산출물도 함께 갱신한다.
