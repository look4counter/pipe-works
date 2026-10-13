# 구현 계획: Batch 실행 프로세스 선택

**날짜**: 2026-10-14 | **명세**: [spec.md](spec.md)

## 요약
Pipeline.run에서 Batch 추론 존재 여부에 따라 기존 _run_local 또는 run_remote를 선택한다. 추론 엔진과 단계 실행을 복제하지 않는다.

## 기술 환경
Python 3.11.9, Windows, PyTorch CUDA, cloudpickle, watchdog, unittest를 사용한다. 새로운 의존성과 영구 저장소는 없다. 일반 실행에서는 중앙 연결 및 직렬화 비용을 제거한다.

## 헌장 점검
헌장은 미작성 양식이므로 규범 검사는 생략한다. 저장소의 한글 문서와 speckit 절차 지침을 준수한다. 설계 후에도 위반은 없다.

## 조사 및 설계
기존 YoloInference는 단건 직접 실행과 Batch 작업자 실행을 이미 지원한다. 원인은 Pipeline.run의 무조건 중앙 실행이다. 단계 트리를 방문 집합과 함께 탐색하고 Hotswap, TapSkipIfBusy, CudaAsync, EveryNFrames를 해제한다. Batch YoloInference 발견 시 중앙 실행을 선택한다. 중앙 모듈은 필요한 경우에만 가져온다.

## 프로젝트 구조와 변경 지점
- src/pipeworks/pipeline.py: Batch 검사와 실행 분기.
- tests/test_pipeline_routing.py: PID·직렬화 불필요·중첩·혼합·그룹 선택 검증.
- tests/test_central_process.py: 중앙 프로토콜 검증은 명시적 run_remote 호출로 유지하고 생성자 검증은 Batch 조건으로 실행한다.
- README.md 및 docs/site의 현재 실행 설명: Batch 기준을 반영한다.
- specs/028-batch-process-routing/: 명세·설계·작업 산출물.

## 검증 전략
실제 GPU 모델을 사용하지 않고 구성과 실행 경로를 검증한다. 먼저 회귀 테스트를 작성하여 실패를 확인한다. 변경 후 라우팅·중앙 프로토콜·설정·추론 테스트를 실행한다. CUDA 실모델 검증은 환경 지원 여부를 별도로 기록한다. 사용자 변경 예제는 보존한다.
