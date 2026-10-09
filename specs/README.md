# 현행 명세와 소스코드 대조

**점검일**: 2026-10-03
**기준**: 현재 `src/pipeworks`, `examples`, `tests`의 동작

## 기능별 문서

| 명세 | 현재 역할 | 확인 상태 |
| --- | --- | --- |
| [002 RTSP 패킷 수신](002-rtsp-packet-source/spec.md) | 첫 비디오 스트림의 유효 패킷을 전달하고 설정에 따라 재연결 | 모의 연결 테스트 있음 |
| [003 YAML 설정과 컨텍스트](003-step-yaml-config/spec.md) | 단계 클래스명으로 설정을 전달하고 동적 컨텍스트를 사용 | 동일 객체 임의 속성 전달 검증 T038 미완료 |
| [004 RTSP 패킷 송출](004-rtsp-publish/spec.md) | 패킷을 RTSP 서버로 전송하고 실패 시 재시도 | 모의 송출 테스트 있음 |
| [005 NVIDIA 인코딩](005-nvidia-encode/spec.md) | GPU 프레임을 PyAV 패킷으로 변환 | 직접 모의 테스트 및 실장비 송출 검증 미완료 |
| [006 NVIDIA 디코딩](006-nvidia-decode/spec.md) | 압축 패킷을 GPU 프레임으로 변환 | 직접 모의 테스트 및 실장비 디코딩 검증 미완료 |
| [007 Step 핫스왑](007-step-hotswap/spec.md) | 사용자 정의 Step만 자동 감시·교체 | 모의 단계 테스트 있음 |
| [009 배경 Tap](009-background-sink/spec.md) | 처리 중이면 새 작업을 버리는 단일 작업자 | 모의 단계 테스트 있음 |
| [010 프레임 보고](010-stream-report/spec.md) | 실행별 FPS·추론·단계별 지연을 두 줄로 출력 | 보고 테스트 있음 |
| [011 동기식 YOLO](011-yolo-detect-sync/spec.md) | 선택 프레임을 CPU BGR로 변환해 단일 추론 | 단계 테스트 있음. 현재 예제에서는 사용하지 않음 |
| [012 중앙 스트림 프로세스](012-central-stream-process/spec.md) | 파이프라인을 중앙 프로세스에서 실행하고 모델별 GPU 배치를 공유 | 통합 테스트 있음. 예제 5개 스트림의 실부하 검증은 별도 필요 |

이전 `008` 문서 묶음은 별도 YOLO 작업자 프로세스와 GPU IPC를 요구했다. 해당 구조는 현행 코드에서 제거되었으며 현재 배치 감지 계약은 [012 명세](012-central-stream-process/spec.md)에 있다.

## 현재 예제 흐름

`RTSPSource → NvidiaDecode → YoloDetectBatch → BoxOverlay → NvidiaEncode → Tap → RTSPPublish → StreamReport`

01 예제는 한 영상, 02 예제는 다섯 영상을 각각 실행한다. 두 예제 모두 `YoloDetectBatch`와 공유 YAML의 해당 섹션을 사용한다. `YoloDetect`는 공개 단계로 남아 있지만 예제에 등록되어 있지 않다.

## 검증 상태

- 2026-10-03 `python -m unittest discover -s tests -v`: 108개 실행, 1개 오류. `test_stream_config_applies_to_single_detector`가 현재 예제에 없는 `YoloDetect` YAML 섹션을 읽으려 한다.
- 003 T038, 005 T009·T011, 006 T006·T007은 작업 목록에서 미완료 상태다.
- 실제 RTSP 입력부터 GPU 디코딩·추론·인코딩·송출까지의 다중 영상 장시간 부하는 이 테스트 결과만으로 보장되지 않는다.
