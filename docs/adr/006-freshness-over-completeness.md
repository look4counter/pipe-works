# ADR 006: Frame 완전성보다 실시간 최신성 우선

## 상태

Accepted as a core design principle; runtime enforcement is pending.

## 문맥

실시간 영상 Pipeline에서는 모든 Frame을 처리하는 것보다 원본과 합성 영상의
시간 차이를 제한하는 것이 중요하다. GPU 추론, 느린 카메라, encoder, MediaMTX
네트워크 지연이 겹치면 모든 Frame을 보존하는 queue는 처리량을 유지하면서도
출력 영상을 과거 영상으로 만든다.

## 결정

Pipe Works는 **freshness over completeness**를 기본 원칙으로 채택한다.

- Frame에는 입력 timestamp와 stream identity를 보존한다.
- bounded queue를 사용하고 오래된 Frame을 우선 폐기한다.
- batch는 정해진 wait budget 안에서만 구성한다.
- output 직전에 Frame age를 확인한다.
- 목표 end-to-end latency는 기본 운영 기준 1,000ms 이하로 검증한다.
- 지연을 초과한 Frame은 기본적으로 drop하고 metrics에 기록한다.
- Action/이벤트 처리는 video plane과 분리한다.

## 대안과 Trade-off

- 모든 Frame 보존: 분석 완전성은 높지만 실시간성이 무너질 수 있다.
- 무제한 queue: 구현은 단순하지만 장애 시 지연이 계속 누적된다.
- 오래된 Frame drop: 일부 분석 대상은 잃지만 현장 화면의 최신성을 유지한다.

## 구현 상태

bounded queue, `latest` drop policy, batch wait 설정, queue drop metrics는
구현되어 있다. 그러나 Source 수신부터 실제 encoded MediaMTX output까지의
end-to-end age 측정과 1초 freshness budget 강제는 아직 구현해야 한다.

## Acceptance Criteria

1. 입력 timestamp와 output publish timestamp로 end-to-end latency를 계산한다.
2. p50/p95/p99 및 만료 Frame drop 수를 metrics로 제공한다.
3. 부하를 높여도 queue가 무한히 성장하지 않는다.
4. 1초 초과 Frame은 output으로 보내지 않고 최신 Frame을 우선 처리한다.
5. 9-stream Batch 환경에서 Stream ID와 sequence 보존을 유지한다.
