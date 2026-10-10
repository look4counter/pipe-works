# NvidiaDecode: 하드웨어 비디오 디코딩

NVIDIA GPU를 사용해 RTSP 패킷을 디코딩합니다. 내부 스레드에서 수신·디코딩을 계속 수행하며, 대기 프레임을 최대 30개 보관하며 초과 시 가장 오래된 대기 프레임을 버립니다. 별도의 최신 프레임 Step이 필요하지 않습니다.

**파일 위치:** `src/pipeworks/embedded/nvidia_decode.py`  
**역할**: Processing Step (디코딩)

---

## 📚 개요

- NVIDIA GPU 하드웨어 가속 디코딩
- CPU 사용률 감소
- RTSPSource 다음에 배치 (선택사항)

---

## 🔑 사용법

```python
from pipeworks import Pipeline
from pipeworks.embedded import RTSPSource, NvidiaDecode, YoloDetect

pipeline = Pipeline("gpu-decode", config=Path("config.yaml"))
pipeline.step(RTSPSource(url="rtsp://camera"))
pipeline.step(NvidiaDecode())  # GPU 디코딩
pipeline.step(YoloDetect(model_path=Path("models/yolov8n.pt")))
pipeline.run()
```

---

## ⚙️ 설정 (config.yaml)

```yaml
NvidiaDecode:
  gpu_id: 0                  # 사용할 GPU 번호 (기본값 0)
```

---

## 프레임 전달과 메모리

대기 큐는 30개입니다. 소비는 FIFO 순서이며 큐가 가득 차면 가장 오래된 대기 프레임을 제거하고 새 프레임을 추가합니다. 소비 중인 프레임은 제거하지 않습니다. 여러 디코딩 출력과 EOF 출력도 순서대로 게시합니다. 따라서 모든 프레임을 보존해야 하는 녹화 용도에는 적합하지 않습니다.

압축 패킷은 순서대로 디코딩합니다. PyAV 패킷의 원본 버퍼 주소와 크기를 직접 전달하여 Python 바이트 및 ctypes 중간 버퍼 복사를 하지 않습니다. 디코더 호출이 반환될 때까지 패킷 객체를 유지합니다. RTSPSource에서 RTSPPublish로 직접 전달하는 패킷 계약도 유지됩니다. 디코딩 자체가 입력 속도보다 느리거나 수신 이전에 지연이 생긴 경우에는 이 슬롯만으로 지연을 제거할 수 없습니다.

`GetLockedFrame()`으로 디코더 출력 버퍼를 잠그고 같은 GPU 주소의 CUDA `torch.Tensor`를 전달합니다. 이 단계에서는 영상 데이터를 복사하거나 별도 영상 버퍼를 할당하지 않습니다. `Decode()` 결과를 단순히 보관하는 방식은 출력 풀의 재사용을 막지 못하므로 사용하지 않습니다. 텐서는 DLPack으로 재공유할 수 있습니다.

별도 소비 CUDA 스트림이 준비 이벤트를 기다립니다. 후속 처리 뒤 완료 이벤트를 기록하고, 마지막 텐서 참조가 해제되고 GPU 이벤트가 끝난 버퍼만 `UnlockFrame()`으로 반환합니다. 일반 전달 경로에서 CPU가 스트림 전체를 동기화하지 않습니다. 종료 시에는 안전하게 남은 이벤트를 기다립니다.

대기 큐는 최대 30개이며, 소비 중·비동기 소비자 보관·반환 대기를 합친 잠금 출력 버퍼 상한은 34개입니다. 상한에 도달하면 버퍼 반환을 기다립니다. 외부 코드에서 출력을 계속 보관하면 생산이 멈출 수 있으므로 사용한 프레임 참조를 해제해야 합니다. 디코더 내부 참조·재정렬 버퍼 수는 별도입니다.

CudaAsync는 GPU 작업 완료 후 내부 작업 컨텍스트의 원본 프레임 참조를 정리하며, 출력 컨텍스트와 외부에서 보관한 텐서는 유지합니다. 감싸진 Step은 처리에 필요한 프레임을 yield 전에 사용해야 하며, 이후까지 보관하려면 텐서 참조를 별도로 유지해야 합니다. 완료 요청의 생성기 지역 변수 때문에 잠금 버퍼가 소진되는 경우는 내부에서 정리합니다.

설치된 PyNvVideoCodec 2.2.2의 잠금 API를 사용하며, EOF는 길이 0인 패킷으로 지연 프레임을 회수합니다. 공유 레이아웃은 NV12, P016, NV16, P216, YUV444, YUV444_16BIT를 지원하고 크기·행 간격을 검증합니다.

기존 `frame`, `video_stream`, `cuda_stream`, `pixel_format` 속성과 다음 진단 속성을 제공합니다.

| 속성 | 의미 |
|---|---|
| `decoded_at` | 디코딩 출력 게시 시점의 `time.perf_counter()` 값 (GPU 완료 시각은 아님) |
| `processing_started_at` | 후속 단계에 전달하는 시점의 같은 시계 값 |
| `decode_dropped_frames` | 이번 입력 구간에서 소비 전에 교체하거나 건너뛴 프레임의 누적 개수 |

두 시각의 차이는 디코딩 이후 슬롯 대기 시간입니다. 카메라 촬영 시점부터의 지연을 나타내지는 않습니다.

## 오류와 종료

수신·디코딩 오류는 소비자에게 전달합니다. 입력 종료 시 지연 프레임에도 FIFO 큐 정책을 적용합니다. 종료나 핫스왑 시 대기 프레임을 해제하고 작업 스레드가 끝날 때까지 기다립니다.

`RTSPSource`의 재연결 대기는 취소할 수 있습니다. 이미 진행 중인 수신 호출은 기존 수신 타임아웃 또는 다음 패킷을 기다려야 하므로 유한한 수신 타임아웃을 설정해야 합니다. 사용자 정의 입력도 블로킹 읽기가 반환되거나 수신 취소 신호에 협조해야 정상적으로 종료할 수 있습니다.

## 🔗 관련 문서

- [NvidiaEncode](nvidia_encode.md): 인코딩
- [RTSPSource](rtsp_source.md): RTSP 입력
- [Pipeline](../pipeline.md): 파이프라인 조립
