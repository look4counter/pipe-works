# 구현 계획: 1.0.0 릴리즈 기준 고정

**기능**: 1.0.0 릴리즈 기준 고정
**작성일**: 2026-10-27
**명세**: [spec.md](spec.md)

## 요약

현재 main 소스를 최초 1.0.0 릴리즈 기준으로 고정한다. 프로젝트 메타데이터와 uv 잠금 파일의 버전을 맞추고, Python 3.11.9·Windows x64·CUDA 12.1 기준의 requirements 핀 파일을 제공한다. 회사명을 노출하지 않는 사내 독점 LICENSE, 의존성 고지, 릴리즈 노트를 추가한다.

## 기술 맥락

- **언어/버전**: Python 3.11.9
- **패키지 관리자**: uv 잠금 파일과 pip 호환 requirements 핀 파일
- **대상 플랫폼**: Windows x64
- **GPU 기준**: CUDA 12.1, PyTorch 2.2.1+cu121, TensorRT 10.10.0.31
- **테스트**: 메타데이터·핀 파일·문서 구조 검사, Python 문법 검사, 기존 회귀 테스트 가능 여부 확인
- **범위**: pyproject.toml, uv.lock, requirements 파일, LICENSE, THIRD_PARTY_NOTICES.md, RELEASE_NOTES.md
- **제외**: wheel 빌드, wheelhouse 수집, 실행 번들 zip, 체크섬 생성, Git tag와 GitHub Release 게시

## 설계

### 버전

- pyproject.toml의 project.version을 1.0.0으로 변경한다.
- uv.lock의 package metadata version을 uv의 표준 갱신 방식으로 맞춘다.
- 기존 직접 의존성 버전은 변경하지 않는다.

### 핀 파일

- requirements-py311-win-amd64-cuda121.txt를 릴리즈 기준 파일로 제공한다.
- 직접 의존성 및 잠금 파일에서 확인 가능한 전이 의존성을 고정한다.
- PyTorch와 torchvision은 CUDA 12.1 공급 경로를 명시한다.
- uv가 없는 환경에서 자동 생성할 수 없으면 잠금 파일 기반의 수동 산출 범위와 재생성 명령을 문서에 기록한다.

### 법적·배포 문서

- LICENSE는 회사명 없이 Internal and Confidential, 비공개 사용, 복제·재배포 제한, 보증 부인, 저작권 표기를 포함한다.
- 공동 기여자는 look4counter와 lhoris로 표시한다.
- THIRD_PARTY_NOTICES.md는 직접 의존성과 주요 전이 의존성을 표로 정리하고 공식 프로젝트 URL 또는 패키지 메타데이터 확인 경로를 기록한다.
- RELEASE_NOTES.md는 1.0.0 범위, 지원 환경, 설치 기준, 알려진 제한, 이번 릴리즈에 포함하지 않는 산출물을 기록한다.

## 파일 구조

`text
pyproject.toml
uv.lock
requirements-py311-win-amd64-cuda121.txt
LICENSE
THIRD_PARTY_NOTICES.md
RELEASE_NOTES.md
specs/048-release-1-0-0/
`

## 검증 전략

- TOML의 project.version과 uv.lock의 프로젝트 버전을 비교한다.
- requirements 핀 파일의 직접 의존성 버전과 pyproject.toml을 비교한다.
- LICENSE에 회사명 미포함과 두 공동 기여자 표기를 검사한다.
- 서드파티 고지와 릴리즈 노트의 필수 항목을 검사한다.
- Python 문법 검사와 git diff --check를 수행한다.
- 테스트 의존성 또는 uv 부재로 실행 불가한 검증은 원인을 기록한다.

## 복잡성 추적

새 실행 코드나 런타임 복잡성은 추가하지 않는다. 릴리즈 산출물 문서와 버전 메타데이터만 추가한다.
