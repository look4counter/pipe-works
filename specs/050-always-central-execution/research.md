# 조사 결과

- 결정: 모든 run 호출을 기존 run_remote로 보낸다. 근거: batch_server는 이미 항상 유효한 문자열이며 기본값은 production이다. 별도 실행 옵션은 요청 범위를 넘는다.
- 결정: batch는 추론 경로에만 관여한다. YoloInference는 batch 참일 때만 local_yolo_inference.infer를 호출한다. 거짓일 때 개별 세션을 사용하며 변경하지 않는다.
- 결정: 서버의 _run_local(stop)은 유지한다. 기존 main._handle이 이를 호출하므로 재귀적 서버 요청이 없다.
- 결정: _has_batch_inference는 삭제한다. _iter_steps는 다른 용도로 유지한다.
- 검증 제약: 앞선 진단에서 Named Pipe 생성이 WinError 5로 실패했다. 실제 실행 시 재확인하고 통합 검증의 성공을 추정하지 않는다.
