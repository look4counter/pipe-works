# 작업 목록: 후처리 최적화

## 1단계 준비

- [x] T001 환경과 NMS 의미를 검토한다: specs/021-postprocess-optimize/research.md

## 2단계 기반

- [x] T002 독립 참조 비교 테스트를 작성한다: tests/test_tensor_rt_postprocess_optimized.py

## 3단계 사용자 이야기 1

- [x] T003 [US1] 후보 필터와 좌표 연산을 최적화한다: examples/step/tensor_rt_post_process.py
- [x] T004 [US1] 기존 통합 테스트의 전처리 import를 갱신한다: tests/test_tensor_rt_processing.py
- [x] T005 [US1] 독립 기존식 비교 벤치마크를 작성한다: tools/benchmark_postprocess.py

## 4단계 검증

- [x] T006 테스트와 벤치마크 결과를 기록한다: specs/021-postprocess-optimize/quickstart.md

## 의존성과 실행 전략

T001 → T002 → T003 → T004 → T005 → T006 순서로 수행한다. 이야기 1 전체가 최소 제공 범위이다. 통합 테스트와 벤치마크 검토는 독립적으로 수행 가능하다.

## 5단계 수렴 검토

- [x] T007 FR-004 검증의 부분 미완료를 해결한다: tests/test_detection_report.py의 오래된 전처리 import를 현재 공개 클래스로 수정하고 실제 엔진·타임아웃 리포트 검증을 실행한다.
