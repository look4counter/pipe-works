# 검증 안내

Windows와 프로젝트 가상환경을 사용한다.

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -p test_central_process.py
.venv/Scripts/python.exe -m unittest discover -s tests -p 'test_pipeline*.py'
```

검증: 기본 False 호환, 생성자 bool 검증·직렬화 보존·인자 없는 run, 같은 모드 재사용·다른 모드 PID 분리, 동시 시작, 개발 강제 종료 후 운영 지속, 개발 유휴 종료 독립성, 기존 출력·연결 종료·핫스왑 회귀.

운영은 Pipeline(..., development=False), 개발은 Pipeline(..., development=True)로 생성하고 둘 다 pipeline.run()으로 실행한다. 생성자 옵션이며 영상 YAML의 실시간 설정이 아니다. 그룹마다 모델을 로드하므로 GPU 메모리를 추가로 사용한다.

## 이전 실행 옵션 계약의 검증 결과 — 2026-10-11

- 중앙 프로세스: 23개 중 22개 통과, CUDA 조건이 충족되지 않은 GPU 추론 1개 건너뜀.
- 실제 Windows 파이프에서 같은 그룹 재사용·다른 그룹 PID 분리·동시 시작·잘못된 이름 거부를 확인했다.
- 테스트용 개발 서버의 실제 PID를 강제 종료한 뒤 운영 영상 처리 지속을 확인했다.
- 개발 유휴 종료·재시작 중 운영 PID와 영상 처리 유지도 확인했다.
- 파이프라인 회귀 11개 통과. 파일 감시 테스트 하나는 첫 실행에서 실패했으나 코드 변경 없이 전체 재실행에서 통과했다.
- 샌드박스에서는 Windows 파이프 접근 거부로 실패하여 중앙 테스트는 권한 확장 후 실행했다.
- 기존 서버 시작 과정의 표준 오류 읽기 핸들에 ResourceWarning이 출력됐으나 테스트 결과에는 영향이 없었다.
- git diff --check 통과.

## 생성자 개발 모드 계약의 검증 결과 — 2026-10-11

- 중앙 프로세스 23개 중 22개 통과, CUDA 조건이 충족되지 않은 GPU 추론 1개 건너뜀.
- 파이프라인 회귀 11개 통과.
- development 기본 False·bool 이외 값 거부·직렬화 보존·인자 없는 run 계약 통과.
- 생성자 모드에 따른 운영·개발 PID 분리와 동일 모드 재사용을 실제 Windows 연결에서 확인했다.
- 개발 강제 종료와 유휴 종료·재시작 시 운영 영상 지속 검증 통과.
- 기존 표준 오류 핸들의 ResourceWarning은 계속 출력되며 이번 변경 범위 밖이다.
- 수렴 점검에서 요구사항 6개·성공 기준 3개·인수 시나리오 5개와 생성자 변경 계획의 미구현 항목이 없었다.
