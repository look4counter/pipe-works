# 작업 목록: 소스 주석 한글화

## 1단계: 준비

- [X] T001 src/, examples/, tests/, tools/ 및 build.ps1의 영어 설명과 변경 전 구문을 확보한다. (FR-001, FR-002)

## 2단계: 기반 검토

- [X] T002 specs/038-korean-code-comments/spec.md, plan.md 및 tasks.md의 일관성과 설명 번역 범위를 검토한다. (FR-001, FR-002, FR-003)

## 3단계: 사용자 이야기 1

독립 검증: 영어 설명 잔여 검색과 번역 검토를 수행한다.

- [X] T003 [US1] src/pipeworks/의 영어 설명 주석 및 docstring을 번역한다. (FR-001, FR-002)
- [X] T004 [US1] examples/, tests/, tools/ 및 build.ps1의 영어 설명을 번역한다. (FR-001, FR-002)

## 4단계: 최종 검증

- [X] T005 대상 Python 파일의 구문과 일반 문자열 보존, 영어 설명 누락을 검증한다. (FR-003, SC-001, SC-002)

## 의존성과 구현 전략

T001 → T002 → T003 → T004 → T005 순서로 수행한다. T003과 T004는 파일이 분리되어 병렬 작업도 가능하지만 이번에는 순차 수행한다. 최소 완성 범위는 사용자 이야기 1 전체이며 새 테스트는 만들지 않는다.

## 5단계: 사용자 이야기 2

- [X] T006 [US2] src/pipeworks/pipeline.py의 _LiveConfig에 역할, 상태 및 제어 흐름 설명을 추가한다. (FR-004)
- [X] T007 [US2] src/pipeworks/pipeline.py의 변경 전후 AST 동일성과 설명 정확성을 확인한다. (SC-003)

T006은 명세·명확화·계획·일관성 검토 후 수행하고 T007은 T006에 의존한다. 단일 파일이므로 순차 실행한다.
