# 구현 계획: StreamReport 디버그 로그

**명세**: [spec.md](spec.md)
**날짜**: 2026-10-15

## 요약

기존 sys.stdout.write/flush를 logging.getLogger(__name__)의 debug 호출로 전환한다. 메시지 두 줄과 기존 보고 스레드의 문맥을 유지한다.

## 기술 배경

Python 3.11 표준 logging과 기존 unittest를 사용한다. 의존성·저장소·공개 설정 변경은 없다. 기존 주기와 통계 수집 동작을 유지하는 내부 라이브러리 변경이다.

## 원칙 확인

헌법은 미작성 양식이므로 제외한다. 한글 문서와 speckit 단계 순서를 준수한다. 설계 전후 위반 사항이 없다.

## 프로젝트 구조와 구현 단계

1. src/pipeworks/embedded/stream_report.py에 모듈 로거를 추가하고 기존 보고 문자열을 DEBUG 기록으로 전달한다. 전역 로깅 설정은 하지 않는다.
2. tests/test_report.py의 표준 출력 기반 보고 검증을 로깅 캡처로 전환하고 정보 수준 필터링을 검증한다.
3. docs/pipeworks/embedded/stream_report.md에 DEBUG 활성화 방법을 설명한다.
4. 통계 회귀 시험과 Python 구문 및 공백 검사를 수행한다.

## 검증

기존 보고 내용·무출력 입력·종료·통계 계산 시험을 유지하고 DEBUG 기록 및 INFO 필터링을 확인한다. 구현 후 speckit-converge로 대조한다.

## 단일 스트림 예제 후속 계획

examples/01_single_stream_rtsp_style.py에 logging을 가져오고 __main__ 블록에서 logging.basicConfig(level=logging.DEBUG)를 build_pipeline 호출 전에 실행한다. 라이브러리와 예제 모듈 가져오기의 로깅 정책은 유지한다. AST로 진입점 설정과 실행 순서를 확인하고 구문·공백 검사를 수행한다.

## YoloReport 후속 계획

src/pipeworks/embedded/yolo_report.py의 sys.stdout.write/flush를 모듈 logger.debug로 전환한다. 주기 보고와 종료 시 마지막 보고는 같은 출력 경계를 사용하며 기존 다중 행 메시지와 수집 정리를 유지한다. tests/test_detection_report.py의 출력 캡처를 DEBUG 로그 캡처로 갱신하고 INFO 필터링을 확인한다. docs/pipeworks/embedded/yolo_report.md에 모듈별 로그 설정을 설명한다. 기존 표준 logging 방식으로 해결되므로 추가 기술 조사나 데이터 모델 변경은 필요 없다.

## 중앙 프로세스 안내 후속 계획

src/pipeworks/main.py의 serve 중복 실행 안내 print 한 곳을 기존 모듈 로거의 warning 호출로 바꾼다. 문자열과 반환 조건을 유지한다. 기존 안내 경로를 대역으로 실행하여 WARNING 기록과 직접 표준 출력 부재를 검증한다.
