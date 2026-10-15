# 구현 계획: 중앙 프로세스 구조화 로그 중계

**명세**: [spec.md](spec.md)
**날짜**: 2026-10-15

## 요약과 기술 배경

Python 3.11 표준 logging·ContextVar와 기존 cloudpickle/Windows named pipe를 사용한다. 새 의존성이나 공개 생성자 변경 없이 내부 프로토콜을 central-v20으로 올린다. 로그 정책은 요청의 스냅샷이고 수신 핸들러는 호출자에 남는다. 요청별 전역 수준 변경을 피하고 실행별 route에서 필터한다.

## 원칙 확인

헌법은 미작성 양식이라 제외한다. 한글 문서와 speckit 순서를 준수하며 설계 전후 위반 사항은 없다.

## 프로젝트 구조

- src/pipeworks/remote_logging.py: 정책 스냅샷, 실행 경로, 직렬화, 중계 핸들러, 수신 처리 및 줄 단위 stdout 어댑터.
- src/pipeworks/main.py: 요청 봉투, 새 log 메시지, 실행 경로 바인딩과 출력 어댑터 호환 연결, 버전 변경.
- tests/test_remote_logging.py: 정책·직렬화·예외·줄 버퍼·수신·문맥·연결 실패·실행별 격리 시험.
- tests/test_central_process.py: 실제 프로세스의 로그·print·동시 호출·보고·실패 응답 검증.
- tests/test_async.py: 기존 직렬화 봉투와 비동기 문맥 호환 검증.
- docs/pipeworks/main.md 및 보고 문서: 호출자 로그 설정·추가 필드·호환 print·범위 설명.

## 설계

1. 요청은 pipeline, logging, execution_id를 담은 dict로 직렬화한다. 프로토콜 버전 분리로 이전 실행 서버와 통신하지 않는다.
2. 중앙에서 생성된 모듈 로거들의 수준을 한 방향으로 개방하고 루트·비전파 로거에 중계 핸들러를 설치한다. 사전 준비된 기존 핸들러는 활성 실행 중에는 중복 처리하지 않게 필터한다. 각 실행 route가 요청의 루트·이름별 정책을 계산한다. 향후 일반 전파 로거는 루트 경로를 따른다.
3. 로그는 getMessage로 인자를 렌더하고 exc_info는 문자열 exc_text로 변환한다. 기본 출처·시간·스레드/프로세스 필드와 안전한 추가 필드를 dict로 보낸다. 비직렬화 값은 안전한 문자열로 바꾸며 전송 중 예외를 재로깅하지 않는다.
4. 호출자는 logging.makeLogRecord와 원래 로거의 isEnabledFor/handle을 사용한다. 수신 마커로 다시 중계되는 루프를 방지한다. 호출자 핸들러의 수준·필터·포맷터가 최종 출력과 저장을 담당한다.
5. 기존 _ThreadOutput는 print 호환 어댑터 입구로 남긴다. _current_output_writer/_use_output_writer를 통해 기존 라이브러리 작업자에 route를 함께 전달하고 중첩 범위는 복원한다. CudaAsync의 문맥 외부 예외도 worker 범위의 route로 처리한다.
6. stdout 어댑터는 스레드별 줄 버퍼, flush와 마지막 부분 줄, 64KiB 분할을 지원한다. DEBUG 정책은 pipeworks.user_output에 적용한다. 종료 시 전체 버퍼를 비우고 route를 비활성화한 뒤 완료 응답을 보낸다. 지연 작업자 로그는 버린다.
7. 서버의 진단·하트비트·프로세스 그룹과 기존 실패 응답은 유지한다. 로컬 실행에는 중계 핸들러를 설치하지 않는다.

## 검증과 실행 순서

단위 시험을 먼저 작성해 미구현 실패를 확인한다. 구현 후 실제 named pipe 프로세스에서 INFO/DEBUG/예외, 비전파, print, 동시 호출·비동기 Step과 StreamReport를 검증한다. 기존 중앙·비동기·통계·실행 경로 및 처리 경계 시험과 구문/공백 검사를 수행한다. 중대한 실패는 해결 후 진행하고 마지막 speckit-converge로 의도와 코드를 대조한다.
