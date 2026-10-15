# 작업 목록: wheel 빌드 스크립트

## 1단계: 준비

- [X] T001 pyproject.toml과 저장소 루트의 빌드 도구 및 기존 파일명을 확인한다.

## 2단계: 사용자 이야기 1

- [X] T002 [US1] build.ps1에 uv wheel 빌드·출력 경로·오프라인 선택·실패 처리·작업 경로 복원을 구현한다. FR-001~003.

## 3단계: 검증

- [X] T003 build.ps1의 구문과 요구사항을 검사한다. 실제 빌드는 실행하지 않는다. SC-001~002.

## 의존성과 전략

T001 → T002 → T003 순서로 진행하고 마지막 speckit-converge로 대조한다.

## 4단계: Python 버전 지정

- [X] T004 [US1] build.ps1에 --python 3.11.9를 추가하고 pyproject.toml과의 일치·PowerShell 구문·uv 옵션을 검증한다. FR-004, SC-003. T003 이후 수행한다.

## 5단계: Windows 전용 wheel 태그

- [X] T005 [US1] build.ps1의 빌드 백엔드 옵션에 py311 및 win_amd64 태그를 추가하고 구문과 setuptools 태그 계산을 빌드 실행 없이 검증한다. FR-005, SC-004. T004 이후 수행한다.
