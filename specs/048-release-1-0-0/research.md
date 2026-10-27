# 조사: 1.0.0 릴리즈 기준 고정

## 현재 상태

- pyproject.toml의 프로젝트 버전은 0.1.0이다.
- Python 요구 버전은 3.11.9로 고정되어 있다.
- torch와 torchvision은 CUDA 12.1 전용 uv 인덱스를 사용한다.
- uv.lock은 존재하지만 별도의 pip requirements 핀 파일은 없다.
- LICENSE, THIRD_PARTY_NOTICES.md, RELEASE_NOTES.md는 없다.
- build.ps1은 wheel 빌드만 수행하며 릴리즈 번들 생성은 수행하지 않는다.

## 결정

- 이번 작업에서는 현재 직접 의존성 버전을 변경하지 않는다.
- 핀 파일 이름은 대상 환경을 드러내는 requirements-py311-win-amd64-cuda121.txt로 한다.
- 회사명을 쓰지 않고 두 공동 기여자를 표기하는 내부 독점 고지문을 사용한다.
- wheelhouse와 번들 자동화는 별도 릴리즈 후속 작업으로 남긴다.

## 주의사항

uv가 현재 실행 환경에 설치되어 있지 않으므로 uv export를 실행할 수 없다. 핀 파일은 잠금 파일과 pyproject.toml을 근거로 생성하고, 릴리즈 빌드 환경에서는 uv export 또는 동등한 잠금 검증을 다시 실행해야 한다. 서드파티 라이선스는 패키지 메타데이터와 공식 프로젝트 링크를 기준으로 기록하며, NVIDIA·PyTorch 계열의 상업적 재배포 조건은 별도 법무 검토가 필요하다.
