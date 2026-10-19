# 검증 절차

기존 .venv 환경에서 tests/test_embedded_recovery.py와 test_rtsp_source.py, test_rtsp_publish.py, test_nvidia_decode.py, test_nvidia_encode.py, test_yolo_inference.py, test_tensor_rt_inference.py, test_every_n_frames.py, test_async.py, test_tap_skip_if_busy.py, test_invalid_frame_drop.py를 unittest discover로 실행한다. 일반 오류 후 정상 재개·원본 통과·폐기·자원 정리와 GPU 장애 전파를 확인한다.

## 2026-10-20 검증 결과

연결·송출·디코딩·인코딩·직접 추론·TensorRT·주기·비동기·분기·프레임 폐기와 새 복구 테스트 11개 파일이 모두 통과했다. 실제 GPU 코덱·TensorRT 회귀를 포함한다. 원격 래퍼 테스트의 오래된 batch_process 모의 설정은 현재 batch_server API로 갱신했다. 실제 RTSP 서버를 통한 네트워크 종단 간 검증은 수행하지 않았다.

수렴 보완 후 최종 검증: 관련 15개 파일의 277개 테스트가 모두 통과했다. 직접 추론 초기화 실패의 모델 식별자 보존, 최종 보고 실패와 작업자 생성 실패의 원본 통과·다음 프레임 복구를 추가 확인했다. 공유 프로파일 검증도 오류 전파 대신 원본 통과와 오류 기록을 검증하도록 갱신했다.
