# 구현 계획: PatchCore 실행부

작성일: 2026-10-22 · 명세: [spec.md](spec.md)

## 요약
자체 patchcore-v1 체크포인트를 복원하는 실행부를 추가한다.
기존 YoloInference와 공유 배치 경로를 재사용한다.

## 기술 맥락
Python 3.11.9, torch 2.2.1+cu121, torchvision 0.17.1+cu121을 유지한다.
로컬 파일과 CUDA 기반 라이브러리이며 unittest 및 실제 CUDA로 검증한다.
검색 임시 행렬을 패치 256개·메모리 1024개 단위로 제한한다.
성능 수치 보장은 범위 밖이며 점수 호환성과 GPU 전용 실행을 검증한다.

## 원칙 점검
헌법은 미작성 템플릿이므로 강제 원칙이 없다. AGENTS의 한글 문서와 speckit 순서를 따른다.
설계 전후 점검 통과. 사용자 코드와 학습 프로젝트를 변경하지 않는다.

## 단계 및 파일 구조
0. 연구: 학습 구현과 GPU 계약을 비교하고 추가 의존성 없이 복원한다.
1. 설계: 체크포인트·입출력 계약을 정의한다.
2. 구현: src/pipeworks/yolo_backends/patchcore.py 추가,
   src/pipeworks/backend.py와 src/pipeworks/yolo_backend.py에 선택·매핑 추가.
3. 검증: tests/test_patchcore_backend.py에 기준 구현 비교, 로딩·입력 오류,
   GPU 감시, 단일 및 공유 배치 테스트를 작성한다.
4. 문서: docs/pipeworks/backend.md와 yolo_backends 문서에 계약을 설명한다.

## 복잡성 관리
별도 Step, anomalib, 학습 도구 의존성 없이 기존 실행 계약을 사용한다.
