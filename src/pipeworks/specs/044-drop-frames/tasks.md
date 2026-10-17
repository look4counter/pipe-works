# 작업 목록: 프레임 선택 및 폐기

## 1단계: 준비와 기반

- [x] T001 명세 및 명확화 결과를 specs/044-drop-frames/spec.md에 기록한다.
- [x] T002 설계와 공개 계약을 specs/044-drop-frames/plan.md 및 contracts/python.md에 기록한다.

## 2단계: 사용자 이야기 1

- [x] T003 [US1] specs/044-drop-frames/test_drop_frames.py에서 선택, 설정, 경계 및 재사용을 검증한다.
- [x] T004 [US1] embedded/drop_frames.py에 설정 검증과 프레임 선택을 구현한다.
- [x] T005 [US1] embedded/__init__.py에 공개 Step을 등록한다.

## 3단계: 검증 및 마무리

- [x] T006 새 검증 및 기존 회귀 검증을 실행하고 specs/044-drop-frames/validation.md에 기록한다.

## 의존성과 실행 전략

T001 → T002 → T003 → T004 → T005 → T006 순서로 수행한다.
단일 사용자 이야기이므로 병렬 작업 없이 전체 기능을 검증한다.
