# 빠른 시작: 1.0.0 릴리즈 기준 검증

## 메타데이터 확인

`powershell
Get-Content pyproject.toml
Get-Content requirements-py311-win-amd64-cuda121.txt
`

## 설치 기준

Python 3.11.9와 Windows x64 환경에서 CUDA 12.1에 맞는 NVIDIA 드라이버를 준비한다. PyTorch·torchvision은 CUDA 12.1 전용 공급 경로를 사용한다.

uv가 설치된 빌드 환경에서는 다음 명령으로 잠금 파일과 프로젝트 버전을 검증한다.

`powershell
uv lock --check
uv export --locked --format requirements-txt --no-emit-project --output-file requirements-py311-win-amd64-cuda121.txt
`

## 문서 확인

- LICENSE: 사내·비공개 독점 배포 조건
- THIRD_PARTY_NOTICES.md: 의존성 고지
- RELEASE_NOTES.md: 1.0.0 범위와 제한
