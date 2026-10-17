# 구현 계획: 배치 서버 옵션명 변경

Python 3.11.9, 기존 unittest와 cloudpickle을 사용하며 의존성 추가는 없다.
기존 specs/041-batch-process-alias의 동작과 설계를 유지하고 이름만 변경한다.
헌장은 미작성 템플릿이며 한글 문서 및 speckit 단계 순서를 적용한다.

## 구조 및 설계

- pipeline.py: 생성자, 필드, 검증 메시지 이름 변경.
- main.py: run_remote의 속성 접근 변경. 내부 server_group 유지.
- specs/045-batch-server/remaining.patch: examples, docs, README, tests와 기존 관련 명세의 갱신 패치.
- specs/045-batch-server/verify.py: 임시 복사본에서 변경된 기존 테스트 실행. 원본 테스트는 쓰지 않는다.

## 검증 전략

기존 별칭 생성자 계약, 직렬화, 라우팅, 비동기 테스트를 새 이름으로 실행한다.
구형 인자 거부 및 run_remote가 새 별칭을 실제 연결에 전달하는지도 확인한다.
자동 도구의 feature.json 쓰기는 권한 범위 밖이므로 경로를 명시한 수동 단계로 진행한다.
