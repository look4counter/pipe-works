# 구현 계획: RunOnce Step 래퍼

**기능**: RunOnce Step 래퍼
**작성일**: 2026-10-21
**명세**: [spec.md](spec.md)

## 요약

기존 Step을 감싸서 하나의 래퍼 인스턴스가 최초 입력에 대해서만 내부 Step을 실행하고, 이후 입력을 원본 그대로 전달하는 RunOnce 내장 래퍼를 추가한다. 기존 래퍼가 사용하는 핫스왑·설정 감시 탐색 경로에 단일 내부 Step을 노출해 파이프라인 등록과 중앙 프로세스 실행에서 동일하게 동작하도록 한다.

## 기술 맥락

- **언어/버전**: Python 3.11
- **주요 의존성**: 기존 pipeworks.models.Step, pipeworks.hotswap.Hotswap
- **저장소**: 없음
- **테스트**: pytest
- **대상 플랫폼**: 기존 Pipe Works 실행 환경
- **프로젝트 유형**: Python 스트리밍 파이프라인 라이브러리
- **성능 목표**: 단회 실행 완료 뒤 입력당 추가적인 내부 Step 호출·버퍼링을 발생시키지 않는다.
- **제약**: 기존 Step의 입력/출력 계약과 설정 감시 경로를 유지한다.
- **범위**: 내장 RunOnce 클래스, 공개 export, 파이프라인 래퍼 탐색 통합, 단위·통합 회귀 테스트, 사용자 문서

## 헌법 점검

프로젝트 헌법은 템플릿 상태이며 적용 가능한 규범이 없다. 기존 프로젝트의 테스트 관례와 Step 계약을 따른다.

## 설계

### 실행 모델

1. RunOnce(step) 생성 시 인자로 받은 객체가 Step인지 검증한다.
2. 내부 Step은 기존 래퍼 관례에 따라 이미 Hotswap이거나 내장 Step이면 그대로 사용하고, 그 외에는 핫스왑 래퍼로 감싼다.
3. process(inputs)가 최초로 입력을 받으면 첫 컨텍스트 하나만 내부 Step의 입력으로 전달한다.
4. 내부 Step의 출력은 모두 그대로 내보낸다. 내부 처리가 정상 종료한 뒤에만 실행 완료 상태를 기록한다.
5. 내부 실행 성공 후 남아 있는 입력과 이후 process 호출의 입력은 내부 Step을 거치지 않고 그대로 내보낸다.
6. 최초 입력이 없으면 내부 Step을 호출하지 않고 완료 상태도 기록하지 않는다.

### 상태와 오류

- 상태는 RunOnce 인스턴스의 _ran 불리언으로 보유한다.
- 내부 Step이 예외를 발생시키면 _ran은 False로 유지하고 예외를 그대로 전파한다.
- 동시 호출 동기화는 범위에 넣지 않는다. 기존 파이프라인의 단일 소비 흐름을 전제로 한다.

### 파이프라인 통합

- src/pipeworks/embedded/run_once.py를 추가한다.
- embedded/__init__.py에서 RunOnce를 공개한다.
- pipeline.py의 Step 탐색, 내부 설정 적용, 설정 감시 갱신에서 RunOnce._hot_steps를 재귀적으로 처리한다.
- 중앙 실행 경로의 래퍼 탐색에서도 RunOnce를 기존 CudaAsync·EveryNFrames와 같은 내부 Step 컨테이너로 취급한다.
- RunOnce 자체에는 별도 YAML 옵션을 추가하지 않으며 내부 Step 설정은 기존 클래스명 섹션으로 적용한다.

## 파일 구조

```text
src/pipeworks/embedded/run_once.py       # RunOnce 구현
tests/test_run_once.py                   # 단위·래퍼 조합 테스트
src/pipeworks/embedded/__init__.py       # 공개 export
src/pipeworks/pipeline.py                # 탐색·설정·감시 통합
src/pipeworks/main.py                    # 중앙 실행 경로 통합
docs/pipeworks/run_once.md                # 사용 예시와 계약
specs/046-run-once/                      # 기능 산출물
```

## 테스트 전략

- 여러 입력에서 내부 Step 호출 횟수와 출력 순서를 검증한다.
- 빈 입력, 내부 예외, 다중 출력, 재호출, 서로 다른 인스턴스의 독립성을 검증한다.
- RunOnce export와 파이프라인 설정·탐색 경로를 검증한다.
- 기존 테스트 전체를 실행하고, 환경 의존성으로 전체 실행이 불가능하면 관련 테스트 결과와 실패 원인을 기록한다.

## 복잡성 추적

추가 복잡성 없음. 기존 래퍼의 _hot_steps 및 설정 감시 확장 지점을 재사용한다.
