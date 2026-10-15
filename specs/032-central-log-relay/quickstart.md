# 검증 안내

.venv/Scripts/python.exe -X utf8 -m unittest discover -s tests -p test_remote_logging.py 로 정책·버퍼·문맥·수신 시험을 실행한다. test_central_process.py로 실제 별도 중앙 프로세스의 print/로그/동시 호출/종료를 검증한다.

추가 회귀 대상은 test_async.py, test_report.py, test_detection_report.py, test_pipeline_routing.py, test_processing_boundary.py 및 test_central_yolo_inference.py다. 로그를 보려면 호출자에 logging 핸들러와 적절한 수준을 설정한다. print 호환 로그는 DEBUG다.

## 검증 결과 (2026-10-15)

로그 중계 단위 11개, 비동기 40개, 중앙 실행 30개(기존 29개 전체 실행과 추가 파일 핸들러 시험), 공유 GPU 배치 3개, 일반 통계 22개, 감지 통계 19개, 실행 경로 5개, 처리 경계 3개로 총 133개 고유 시험을 통과했다. TensorRT·TorchScript·Ultralytics 실제 중앙 배치와 DEBUG 보고 전달, 실행별 레벨 격리, 예외 출처, 파일 핸들러, print 부분 줄, 중첩 문맥, 연결 실패 및 재귀 보호를 검증했다. 변경 Python 6개 파일의 구문 검사와 git diff --check를 통과했다.

중앙 실행 회귀에서 기존 stderr 수집 경로의 닫히지 않은 reader 및 종료 중 subprocess에 대한 ResourceWarning이 관측됐으나 모든 시험은 통과했다. 네이티브 stdout/stderr 출력과 실제 카메라 송출 시험은 이번 변경 범위에 포함하지 않았다.
