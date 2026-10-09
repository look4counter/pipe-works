# 조사 결과

- 결정: YOLO Predictor.inference와 postprocess에서 모델 실행과 NMS를 분리한다. 기존 model.predict 전체 StreamReport 통계는 유지한다.
- 근거: 기존 두 추론 통계는 NMS 포함 여부가 달라 비교에 부적합하다.
- 결정: 배치 측정은 콜백으로 호출 범위에 반환한다. 작업자 기본 범위는 다른 스트림 통계를 섞을 수 있다.
- 결정: CUDA Event.query가 참인 경우만 elapsed_time을 읽는다. 추가 synchronize를 넣지 않는다.
- 대안: 결과 객체만 읽는 Report는 타임아웃 후 작업을 관측하지 못하므로 채택하지 않는다.
- 조사 방식: 기존 코드와 설치된 Ultralytics 소스를 읽고 조사 에이전트로 비동기·배치 함정을 검토했다.
