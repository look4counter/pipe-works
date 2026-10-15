# 조사 결과

기존 pyproject.toml과 uv 기반 프로젝트 구성을 확인했다. uv build --wheel을 반복 가능한 스크립트로 제공한다. 자동 의존성 설치나 환경별 하드코딩 캐시 경로는 포함하지 않는다. Offline은 캐시에 빌드 의존성이 있을 때만 성공한다.

명시 플랫폼 태그는 설치된 setuptools 80.9.0의 bdist_wheel.get_tag에서 순수 Python 패키지에도 적용된다. --python-tag=py311, --plat-name=win_amd64를 uv의 반복 --config-setting으로 빌드 백엔드에 전달한다. 이는 바이너리 확장으로 컴파일하는 기능이 아니라 배포 호환성 태그 지정이다.
