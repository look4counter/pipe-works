# 구현 계획

## 공유 모델 경로 캐시

`src/pipeworks/model_worker.py`에 공유 작업자 조회 헬퍼를 둔다. 입력 Path와 상대경로일 때 호출 시 캡처한 CWD를 별칭 키로 사용한다. 모듈별 기존 _workers와 _workers_lock, 새 _worker_paths를 전달한다. 잠금 안에서 별칭→정규 경로→작업자를 조회해 존재하면 즉시 반환한다. 미스는 캡처한 CWD를 기준으로 resolve하고, 정규 경로의 작업자가 없을 때만 is_file과 factory를 수행한다. 작업자 생성 성공 후 별칭을 저장한다. 정규 레지스트리가 초기화된 경우 오래된 별칭만으로 반환하지 않고 다시 준비한다.

`local_yolo.py`와 `local_tensor_rt.py`의 기존 작업자 조회를 이 헬퍼로 대체한다. TensorRT 입력·GPU 이벤트·요청 생성 순서를 유지하며 작업자 조회 이전의 반복 파일 검사를 제거한다. 잘못된 입력 검증은 작업자 생성 전에 수행한다. 실제 최초 로드와 세션 재로드의 파일 읽기는 그대로 둔다. `tests/test_model_worker.py`에서 CPU 모의 작업자로 경로·동시성·오류를 검증하고 두 local 모듈 테스트에서 실제 GPU 입력과 모의 모델로 파일 삭제 후 재사용을 검증한다. 경로 공유·별칭 고정 계약을 YOLO·TensorRT 문서에 반영한다. 추가 의존성은 없고 헌장은 미작성 템플릿이며 문서는 한글로 작성한다.

src/pipeworks/local_tensor_rt.py에 엔진 경로별 작업자 레지스트리·요청 객체·infer API를 구현한다. batch_collector.collect_batch를 재사용하고 _EngineSession으로 플러그인·동적 형상·GPU 출력을 처리한다. 입력은 장치·자료형·형상 메타데이터로 호환 키를 생성하고 축 0으로 cat한다. 출력은 첫 차원이 배치 크기와 같은지 검사하여 배치 1 슬라이스 복제로 분리한다. 추론 통계는 작업자에서 격리하고 호출자의 완료 콜백에 경과 시간을 전달한다. local_yolo처럼 데몬 작업자와 엔진은 중앙 프로세스 수명 동안 공유한다. 별도 종료 API는 이번 범위에서 추가하지 않는다. tests/test_local_tensor_rt.py는 모의 세션과 실제 CUDA로 수집·분리·오류 복구를 검증한다.
