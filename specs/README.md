# 기능 스펙 안내

이 디렉터리는 Pipe Works의 단계별 개발 산출물이다. 각 기능 디렉터리는
요구사항 문서, 구현 계획, 작업 목록, 체크리스트를 포함한다.

새로운 스펙은 한국어를 기본 언어로 작성한다. 기존 스펙은 과거 개발 slice의
추적성과 에이전트 인수인계를 위해 보존하며, 동작이 바뀌면 관련 문서와
테스트를 함께 갱신한다.

## 완료된 개발 slice

- 001: 에이전트 SDK 기반
- 002: 읽기 쉬운 Pipeline DSL
- 003: 실시간 큐, Backpressure, Frame Drop 정책
- 004: 명령 기반 하네스 게이트
- 005: Pipeline 생명주기
- 006: 런타임 메트릭
- 007: 개발자 예제와 테스트용 Source
- 008: GStreamer RTSP 어댑터 경계
- 009: Inference 어댑터 경계
- 010: Output과 Action 어댑터 경계
- 011: HTTP Action 재시도와 신뢰성
- 012: 예제 실행 하네스
- 013: 품질 검사 CLI
- 014: Pipeline 텍스트 다이어그램
- 015: 예제 프로젝트 생성 CLI

## 다음 권장 slice

다음 구현은 AGENTS.md의 권장 순서를 따른다.

1. DSL 선언과 실행 계획을 분리하는 Pipeline.compile()과 PipelinePlan
2. Source, Inference, Action, Output 워커 런타임 골격
3. Pipeline 구성 조기 검증
4. 실제 GStreamer, Ultralytics, TensorRT, MediaMTX 어댑터 심화
5. 메트릭 Snapshot, JSON, Prometheus 출력

모든 slice는 구현, 테스트, 문서 갱신, 커밋, push까지 하나의 완료 단위로 처리한다.
