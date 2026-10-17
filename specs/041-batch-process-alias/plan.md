# 구현 계획: 배치 프로세스 별칭

## 요약과 기술 맥락
Python 3.11.9의 Windows GPU SDK이다. Pipeline의 development 인자를 batch_process 문자열로 대체하고 main.run_remote에서 해당 별칭을 server_group으로 전달한다. 추가 의존성은 없다.

## 규칙 검토
한글 문서와 speckit 절차를 적용한다. 헌법은 미작성 템플릿이다. 설계 전후 규칙 위반은 없다.

## 구조와 설계
- src/pipeworks/pipeline.py: 생성자 인자·필드·기존 그룹과 동일한 유효성 검증. 로컬 실행에서 main을 불필요하게 가져오지 않는다.
- src/pipeworks/main.py: 별칭을 서버 연결·기동에 전달한다. 기존 설치 경로·SID 기반 주소와 별칭 해시·잠금 규칙은 유지한다.
- examples/01_single_stream_rtsp_style.py: 문자열 별칭을 명시한다.
- tests/test_central_process.py: bool 계약을 문자열 계약으로 바꾸고 두 임의 별칭의 실제 PID 격리를 검증한다.
- tests/test_async.py 및 관련 라우팅·중앙 실행 검증과 README.md, docs/pipeworks/ 문서를 갱신한다.

## 검증
생성자·직렬화·원격 연결 인자·로컬 라우팅을 먼저 검증한다. 실제 중앙 프로세스의 같은 별칭 공유, 다른 별칭 분리, 종료 격리를 검사하고 관련 회귀 테스트를 실행한다.
