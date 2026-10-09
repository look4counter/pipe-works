# 실행 및 검증 안내

## 최신 무복사 정책

CudaAsync(*steps, timeout_ms=5)를 사용한다. 정상 결과는 같은 원본 객체에 적용한다. 타임아웃 시 원본 영상 사용 완료가 확인되면 원본을 전달하고 아직 사용 중이면 해당 프레임만 폐기한다. 작업자가 바쁜 동안 후속 입력은 그대로 전달한다. 보호 복사·미완료 복사 목록·복사 정리 스레드는 제거됐다.

YOLO 개별·배치와 예제 TensorRTPreProcess는 RGB 생성 직후 release_frame 이벤트를 보낸다. 같은 CudaAsync의 후속 Step은 원본을 다시 사용하지 않는다. BoxOverlay는 바깥에 둔다. RGB 생성과 배치 텐서 stack 등 모델 입력 생성은 유지한다.

## 작업 절차 기록

기존 014 명세를 최신 요구사항으로 갱신하고 모호성 검토를 수행했다. RTG는 RGB로 해석하며 이벤트 미완료 시 프레임 폐기는 앞선 안전 계약을 따른다. 추가 질문은 없었다. 명세·계획·데이터 모델·계약·작업 목록의 일관성을 분석했고 이전 복사 정책은 대체 관계로 정리했다. 미작성 헌법 템플릿과 존재하지 않는 확장 후크는 생략했다.

구현 전 test_frame_release.py의 신규 5개 테스트를 실행해 기존 구현에서 신호 API 누락, 타임아웃 원본 동일성 실패 및 YOLO 배치 NV12 제출 실패를 확인했다. 구현 후 요청별 신호, 완료·미완료·조회 실패 이벤트, 원본 동일성, 늦은 결과 격리, 복수 Step, DLPack 수명과 CUDA 정리 실패를 검증한다.

## 검증 명령

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -p test_async.py
.venv/Scripts/python.exe -m unittest discover -s tests -p test_frame_release.py
.venv/Scripts/python.exe -m unittest discover -s tests -p test_yolo_detect.py
.venv/Scripts/python.exe -m unittest discover -s tests -p test_yolo_batch.py
.venv/Scripts/python.exe -m unittest discover -s tests -p test_local_yolo.py
.venv/Scripts/python.exe -m unittest discover -s tests -p test_tensor_rt_processing.py
.venv/Scripts/python.exe -m unittest discover -s tests -p test_tensor_rt_inference.py
.venv/Scripts/python.exe -m unittest discover -s tests -p test_local_tensor_rt.py
```

실제 RTSP 영상의 장시간 정지 재현과 GPU 사용률 추세는 별도 운영 검증이 필요하다.

## 최종 검증 결과

2026-10-09: 관련 테스트 152개 실행 결과 통과했으며 실제 YOLO 모델 파일이 없는 2개는 건너뛰었다. 실제 TensorRT 엔진 생성·추론, 전후처리·배치·모델 스트림·핫스왑·YAML 변경·원본 수명을 포함한다. 마지막 완료 조건 보강 후 CudaAsync 및 종료 신호 43개를 다시 실행해 모두 통과했다.

CudaAsync에서 clone·deepcopy·보관 목록·복사 정리 스레드가 없음을 확인했다. 원본 영상 종료 이벤트는 RGB 생성 이후 기록되며 완료가 확인돼야 전달한다. GPU 정리 성공과 작업자 종료는 별도 상태로 관리해 정리 실패 또는 아직 정리 중인 입력을 잘못 전달하지 않는다. 예제 파이프라인의 사용자 YOLO 선택은 보존했고 BoxOverlay가 CudaAsync 바깥에 있는지 검증한다.

명세의 무복사·종료 신호·폐기·수명·복수 단계 요구사항과 현재 구현·테스트를 비교한 수렴 점검에서 남은 구현 작업은 없다. git diff --check도 통과했다.
