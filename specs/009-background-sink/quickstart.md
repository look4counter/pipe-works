# 실행 확인

1. `examples/01_single_stream_rtsp_style.py`의 `Sink(PostProcess())` 구성을 확인한다.
2. 지연을 이벤트로 제어하는 간단한 Step을 `Sink`로 감싸 여러 컨텍스트를 연속 전달한다.
3. 주 스트림 출력이 지연 없이 모두 전달되고, 작업 중 입력은 감싼 Step에 도달하지 않는지 확인한다.
4. 작업 완료 후 새 컨텍스트가 감싼 Step에 도달하는지 확인한다.
