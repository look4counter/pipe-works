# 구현 계획

src/pipeworks/local_tensor_rt.py에 엔진 경로별 작업자 레지스트리·요청 객체·infer API를 구현한다. batch_collector.collect_batch를 재사용하고 _EngineSession으로 플러그인·동적 형상·GPU 출력을 처리한다. 입력은 장치·자료형·형상 메타데이터로 호환 키를 생성하고 축 0으로 cat한다. 출력은 첫 차원이 배치 크기와 같은지 검사하여 배치 1 슬라이스 복제로 분리한다. 추론 통계는 작업자에서 격리하고 호출자의 완료 콜백에 경과 시간을 전달한다. local_yolo처럼 데몬 작업자와 엔진은 중앙 프로세스 수명 동안 공유한다. 별도 종료 API는 이번 범위에서 추가하지 않는다. tests/test_local_tensor_rt.py는 모의 세션과 실제 CUDA로 수집·분리·오류 복구를 검증한다.
