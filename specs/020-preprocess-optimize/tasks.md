# 작업 목록: 범용 전처리 최적화

## 1단계 준비

- [x] T001 명세와 환경을 검토한다: specs/020-preprocess-optimize/spec.md

## 2단계 기반

- [x] T002 독립 참조식과 옵션 조합 테스트를 추가한다: tests/test_tensor_rt_preprocess_optimized.py

## 3단계 사용자 이야기 1

- [x] T003 [US1] 상수 캐시·항등 연산 생략·소유 텐서 정규화를 구현한다: src/pipeworks/embedded/tensor_rt_preprocess.py
- [x] T004 [US1] GPU 비교 벤치마크를 추가한다: tools/benchmark_preprocess.py

## 4단계 마무리

- [x] T005 관련 테스트와 벤치마크를 실행하고 결과를 기록한다: specs/020-preprocess-optimize/quickstart.md

## 의존성과 실행 전략

T001 → T002 → T003 → T004 → T005 순서로 수행한다. 단일 사용자 이야기 전체가 최소 제공 범위이다. 구현 이후 테스트 검토와 벤치마크 검토는 서로 독립적으로 진행할 수 있다.
