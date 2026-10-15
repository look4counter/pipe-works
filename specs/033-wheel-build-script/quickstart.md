# 사용법

저장소 루트에서 다음 명령을 실행한다.

~~~powershell
.\build.ps1
.\build.ps1 -OutputDirectory artifacts
.\build.ps1 -Offline
~~~

기본 산출물 위치는 dist다. uv가 필요하며 처음 빌드할 때는 빌드 의존성 다운로드를 위한 네트워크가 필요할 수 있다. 이번 작업에서는 실제 빌드를 실행하지 않고 구문만 검증한다.

빌드는 --python 3.11.9로 Python 버전을 명시한다. uv 옵션과 PowerShell 구문·버전 인자를 검증했으며 실제 빌드는 실행하지 않았다.

생성 파일명은 pipe_works-0.1.0-py311-none-win_amd64.whl 형태다. Windows x64 플랫폼과 Python 3.11 태그를 지정하며 정확한 Python 3.11.9 제한은 메타데이터로 유지한다. PowerShell 구문·setuptools 옵션 전달·태그 계산을 검증했으며 실제 빌드는 실행하지 않았다.
