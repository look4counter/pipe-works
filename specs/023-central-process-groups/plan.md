# 구현 계획: 중앙 프로세스 그룹 분리

**작성일**: 2026-10-11 | **명세**: [spec.md](spec.md)

## 요약

Pipeline 생성자에 키워드 전용 development: bool=False를 추가하고 인스턴스에 보관한다. run은 인자 없이 호출한다. run_remote는 Pipeline의 development를 내부 production·development 그룹으로 변환한다. 내부 주소·잠금·시작·수명 구현은 유지하며 공개 임의 그룹 선택 옵션을 제거한다.

## 기술 맥락

- Python 3.11.9, Windows Server, 기존 AF_PIPE·msvcrt 잠금·subprocess·cloudpickle 사용.
- 영구 저장소 없이 임시 시작 잠금 파일만 그룹별로 분리한다.
- unittest로 실제 파이프와 PID·강제 종료 격리·유휴 종료를 검증한다.
- 영상 데이터는 선택한 중앙 프로세스 안에 머물러 GPU IPC를 추가하지 않는다.
- 그룹마다 모델을 로드하므로 GPU 메모리 사용량이 증가한다.
- 기존 10초 시작 제한과 1초 유휴 종료, 무창 실행, 출력 전달을 유지한다.

## 헌장 점검

헌장은 미작성 템플릿이므로 규범 점검을 생략한다. 모든 새 문서를 한글로 작성하고 명세·명확화·계획·작업·분석·구현·수렴 순서를 적용한다. 설계 후에도 위반 없음.

## 조사와 설계

새 외부 기술이나 미확정 기술 선택은 없다. 로컬 조사 결과는 research.md에 기록한다. 인터페이스와 상태는 data-model.md와 contracts/execution.md를 따른다.

## 프로젝트 구조

- src/pipeworks/pipeline.py: 생성자 bool 검증·상태 저장 및 인자 없는 run.
- src/pipeworks/main.py: 저장된 모드를 내부 그룹에 매핑. 그룹별 주소·잠금·수명 관리는 유지.
- tests/test_central_process.py: 기존 회귀와 실제 프로세스 격리 검증.
- README.md, docs/pipeworks/pipeline.md, docs/pipeworks/main.md: 실행 예와 자원 공유 경계.
- specs/023-central-process-groups/: 명세·설계·작업·검증 안내.

## 구현 단계

1. 그룹 계약과 검증 시나리오를 작성한다.
2. 주소·잠금·시작·서버 내부 재연결 경로에 그룹을 전달한다.
3. Pipeline 생성자 development와 인자 없는 run 계약으로 문서를 갱신한다.
4. 중앙 실행과 파이프라인 회귀를 검증한 뒤 수렴 점검을 수행한다.
