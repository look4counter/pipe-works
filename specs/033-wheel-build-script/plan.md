# 구현 계획: wheel 빌드 스크립트

**명세**: [spec.md](spec.md)

## 요약과 기술 배경

PowerShell의 PSScriptRoot·Push-Location/Pop-Location과 uv build --wheel을 사용한다. OutputDirectory 기본값은 dist이고 Offline 스위치를 제공한다. 새 의존성을 설치하거나 빌드를 직접 실행하지 않는다.

## 원칙 확인

헌법은 미작성 양식이므로 생략한다. 한글 문서와 speckit 단계를 준수한다. 설계 전후 충돌은 없다.

## 구조와 구현

루트 build.ps1에 인자·도구 확인·저장소 경로 기준 출력 경로 해석·빌드 호출·실패 상태 및 디렉터리 복원을 구현한다. 연구 결과는 research.md에, 사용자 실행 방법은 quickstart.md에 기록한다. 표준 PowerShell과 기존 uv 사용이므로 별도 연구 과제나 외부 인터페이스·데이터 모델 변경은 없다.

## 검증

PowerShell 파서로 구문을 검사하고 빌드 인자 및 실패 처리 흐름을 읽기 검증한다. 사용자 지시대로 빌드는 실행하지 않는다. 구현 후 speckit-converge로 요구사항을 대조한다.

## Python 버전 후속 계획

build.ps1의 uv 인자에 --python 3.11.9를 추가한다. 기존 경로·오프라인·오류 처리는 유지한다. 설치된 uv의 도움말에서 옵션을 확인하고 PowerShell 구문 및 인자를 검증한다. 빌드는 실행하지 않는다.

## Windows 전용 태그 후속 계획

build.ps1의 uv config-setting으로 setuptools bdist_wheel의 --python-tag=py311과 --plat-name=win_amd64를 전달한다. 배포 파일명과 내부 WHEEL 태그를 빌드 시 함께 결정하며 파일명을 수동 변경하지 않는다. 설치된 setuptools의 get_tag 구현에서 순수 Python 패키지의 명시 플랫폼 태그 지원을 확인했다. 실제 빌드 없이 옵션 계산과 PowerShell 구문을 검증한다.
