# 검증 안내

YOLO 감지 또는 CudaAsync 뒤에 `.step(YoloDetectReport())`를 추가한다. TensorRT 전처리·추론·후처리 또는 해당 CudaAsync 뒤에 `.step(TensorRTReport())`를 추가한다.

`.venv/Scripts/python.exe -m unittest discover -s tests -p test_detection_report.py`로 통계를 검증한다. 관련 YOLO·TensorRT·비동기 테스트를 실행한 후 실제 스트림에서 전처리, 모델 실행, NMS, 대기·복사를 비교한다. GPU 이벤트를 읽기 위한 동기화가 추가되지 않아야 한다.

## 독립 Report 구현 검증

YoloDetectReport와 TensorRTReport는 각 파일에서 Step을 직접 구현하며 프로파일·통계·ContextVar·출력 루프를 별도로 관리한다. 실행별 저장소도 yolo_detection_stats와 tensor_rt_detection_stats로 분리했다. 공통 detection_profile.py는 삭제했다. 계측 import는 해당 Report 모듈을 사용한다.

독립 활성화·현재 프로파일·저장소 및 실제 감지 리포트 15개, 비동기·보고·전후처리·모델 ID·프레임 해제 111개, TensorRT 직접·배치 35개 테스트가 모두 통과했다. 실행 코드·예제·테스트에 삭제 모듈 참조가 없으며 git diff --check가 통과했다.

## 측정값 중심 출력 검증

두 Report는 표본 없는 구간 및 기간을 생략하고 GPU 값이 있는 경우에만 GPU 필드를 출력한다. 전체·기타는 경과 시간으로 표시한다. 두 Report의 부분 기간·CPU 전용·CPU/GPU·미측정 행 계약과 기존 실제 GPU·배치·출력 종료를 포함한 16개 리포트 테스트가 모두 통과했다. git diff --check도 통과했다.
