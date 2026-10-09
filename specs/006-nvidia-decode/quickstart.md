# 검증 안내: 최신 프레임 디코딩

TensorRT 연속 실행의 메모리 누적 회귀는 `test_repeated_inference_registers_one_allocator_per_binding`에서 출력 바인딩별 등록 수와 이전 출력 내용 보존으로 확인한다. 실제 엔진 반복 실행의 GPU 메모리 안정성은 [조사 결과](research-zero-copy.md)에 기록했다.

기존 파이프라인의 NvidiaDecode를 그대로 사용한다. 별도 큐 Step이나 설정은 필요 없다.

`.venv/Scripts/python.exe -m unittest discover -s tests -p test_nvidia_decode.py`로 생산자 진행과 30개 FIFO·초과 폐기, 잠금 GPU 버퍼 공유, 지연 반환·잠금 상한·EOF·오류·취소를 검증한다. 실제 CUDA와 PyNvVideoCodec를 사용할 수 있으면 테스트 내부에서 합성 H.264를 생성해 실제 NVDEC → 공유 텐서 → NVENC를 검증한다. 영상 clone 호출은 금지하고 포인터 동일성과 후속 디코딩 중 내용 보존을 확인한다. 기존 report·hotswap·RTSP source·감지·인코딩 테스트도 실행한다.

실제 스트림에서는 후속 처리를 느리게 했을 때 decode_dropped_frames가 증가하면서 대기 프레임이 30개 이하이고 순서대로 소비되는지 확인한다. 대기 나이는 processing_started_at - decoded_at이며 GPU 완료 대기나 촬영 시각부터의 지연은 아니다. 생산자 자체가 디코딩 속도를 따라가지 못하는 경우와 이미 쌓인 수신 버퍼는 별도 문제다. 외부 코드에서 프레임을 보관한 경우 사용 후 참조를 해제한다.

Windows 네이티브 테스트는 PyNvVideoCodec 패키지 디렉터리와 torch/lib의 DLL 검색 경로를 해당 테스트 동안 유지한다. 일반 실행의 CUDA/DLL 설정은 기존 배포 환경을 따른다. 실제 카메라의 장시간 FPS·영상 지연은 합성 테스트와 별도로 확인한다.

다단계 정체 회귀 검증은 200개 합성 입력을 실제 디코더 → 세 단계 CudaAsync → 지연 Tap 조합에 전달한다. 타임아웃·부분 종료가 발생해도 모든 입력을 소비하고 작업자가 종료해야 한다. `test_async.py`는 내부 작업 컨텍스트를 정리하면서 원래 출력 프레임과 메타데이터가 유지되는지도 확인한다.
