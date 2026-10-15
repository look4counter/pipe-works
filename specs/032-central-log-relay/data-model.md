# 데이터 모델

## 요청 봉투

pipeline 객체, logging 정책(root 수준·이름별 level/disabled·전역 disable), execution_id 문자열을 포함한다.

## 실행 경로

send 콜백, stop 이벤트, 정책, pipeline_name, execution_id, active 상태를 유지한다. ContextVar로 전달하며 출력 어댑터가 문맥 밖 라이브러리 작업자에도 전달한다. 종료 이후 active는 거짓이다.

## 로그 패킷

name·levelno·levelname·msg·created·pathname·lineno·funcName·process·processName·thread·threadName·exc_text 등 표준 필드와 pipeworks_pipeline·pipeworks_execution_id 및 안전한 extra를 보낸다. args와 exc_info는 비운다. 호출자는 수신 마커를 붙여 복원한다.

## stdout 어댑터

실행 route, 스레드별 부분 문자열, 잠금 및 64KiB 조각 상한을 갖는다. 개행·flush·스레드 범위 종료·실행 종료에서 DEBUG 로그로 비운다.
