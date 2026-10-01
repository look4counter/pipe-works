# ADR-004: Stream 정보를 가진 Context를 런타임의 기준으로 사용한다

## 상태

채택

## 배경

Multi-stream Batch Inference에서는 모든 결과를 원본 stream으로 되돌려야
한다. 사용자가 Batch Collector나 Demultiplexer를 직접 작성해서는 안 된다.

## 결정

모든 Frame과 처리 Context는 stream_id, timestamp, sequence를 가진다.
Inference 결과도 stream_id와 stage를 가진다. Batch Inference는 Context
목록을 받아 각 Context에 대응하는 결과를 반환한다.

## 검토한 대안

- 별도 테이블에 stream 정보를 보관하기: 특정 런타임에서는 효율적이지만 누락과 불일치에 취약하다.
- Demultiplex를 사용자에게 맡기기: 내부 복잡성을 노출하고 DSL 목표를 어긴다.

## 결과

Context 객체가 Component 사이의 안정적인 경계가 된다. 메타데이터가 조금
늘어나지만 결과 매핑의 정확성과 사용성이 크게 좋아진다.
