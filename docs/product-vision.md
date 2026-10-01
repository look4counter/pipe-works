# 제품 비전

Pipe Works는 **실시간 영상 처리 Pipeline을 선언적으로 구성하기 위한 Python SDK**다.

SDK 사용자는 RTSP, 파일, synthetic source 같은 입력을 연결하고, bounded queue, AI inference, overlay, action, output, metrics를 조합해 안정적인 영상 처리 Pipeline을 만들 수 있어야 한다.

## 우리가 만드는 것

- RTSP, 파일, synthetic, mock source 추상화
- SDK가 소유하는 `Frame`, metadata, detection result 계약
- freshness를 우선하는 bounded queue와 drop policy
- local/remote/fake AI inference provider adapter
- 느린 외부 hook이 영상 경로를 막지 않도록 하는 async action
- start, stop, drain, reconnect, error를 포함하는 lifecycle
- FPS, queue depth, dropped frame, latency, error, health metrics
- 각 기능 slice가 완료되기 전에 동작을 증명하는 harness

## AI Agent가 하는 일

AI Agent는 제품 도메인이 아니다. AI Agent는 SDK를 빠르게 개발하기 위한 엔지니어링 실행 계층이다.

반복 루프:

```text
spec -> task -> implementation -> harness evidence -> decision/doc update
```

목표는 human gate를 줄이는 것이다. 단, Public API 직관성은 절대 희생하지 않는다.

## Human Gate 기준

사람에게 확인해야 하는 경우는 다음으로 제한한다.

- credential 또는 외부 계정 필요
- destructive operation 필요
- production 영향이 있는 배포/작업
- breaking public API change
- acceptance criteria 모순
- retry budget 이후에도 architecture evidence가 불충분한 경우
