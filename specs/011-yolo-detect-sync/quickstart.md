# 동기 감지 검증 안내

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -p test_yolo_detect.py -v
.venv/Scripts/python.exe -m unittest discover -s tests -p test_tensor_rt_inference.py -v
.venv/Scripts/python.exe -m unittest discover -s tests -p test_async.py -v
```

이벤트로 초기화·추론을 막아 해제 전 결과가 반환되지 않는지 확인한다. GPU 크기·좌표·CPU 복사 금지와 호출 문맥의 통계를 검증한다. 공통 Async로 감싸면 지연·오류 원본 통과가 적용되어야 한다. TensorRT 기존 시간 제한 테스트도 통과해야 한다. 실제 모델 또는 CUDA가 없는 검증은 조건부로 건너뛴다.

## 2026-10-09 검증 결과

- 단일 감지 14개 실행: 통과, 실제 YOLO 엔진 부재로 1개 건너뜀. 실제 `.pt` 모델, 호출 스레드·초기화와 추론 대기·오류 전파·입력 검증·GPU 좌표·통계·Async 조합을 확인했다.
- TensorRT 12개 실행: 모두 통과. 실제 원시 GPU 엔진과 기존 지연·오류 통과 동작을 유지했다.
- Async 19개, 공유 GPU 추론 6개, 배치 감지 16개 실행: 실패 없음. 공유 GPU 추론의 YOLO 엔진 검증 1건을 파일 부재로 건너뛰었다.
- 전체 회귀: 156개 실행, 오류 1개·건너뜀 3개. 이전 실행에서 실패했던 중앙 서버 종료 검증은 이번에는 통과했다.
- 전체 오류는 `test_example_places_configured_overlay_before_encoder`의 기존 예제 기대 불일치이다. 테스트는 `YoloDetectBatch`를 기대하지만 현재 예제는 `YoloDetect`를 사용한다. 이번 작업에서는 예제와 이 테스트를 변경하지 않았다.
- 전체 검증은 Windows 명명된 파이프 접근을 위해 기존 승인 범위에서 샌드박스 밖에서 실행했다.
- `git diff --check` 통과. 현재 요구사항 11개·성공 기준 5개와 구현을 대조하여 남은 미구현 항목이 없음을 확인했다.
# 선택적 배치와 입력 사용 종료 신호 검증

2026-10-09 후속 요청은 다음과 같이 사용할 수 있다.

```python
YoloDetect(model_path)  # 기존 개별 동기 추론
YoloDetect(model_path, batch=True)  # 기존 공유 배치 처리
Async(YoloDetect(model_path, batch=True), timeout_ms=10)
```

최종 집중 검증은 Async 28개, YoloDetect 20개, 기존 YoloDetectBatch 16개, 공유 작업자 6개에서 실패 없이 통과했다. 엔진 파일 부재로 YOLO와 공유 작업자 검증에서 각 1개를 건너뛰었다. 실제 CUDA에서 배치 복사 후 타임아웃의 추가 복사 생략과 후속 원본 변경 격리, 복사 전 타임아웃의 기존 복사 유지, 모델 공유와 배치 구성을 확인했다.

선택적 신호의 요청 격리, 이전 실행 문맥의 지연 신호 무시, GPU 이벤트 미완료·조회 실패 복구, 일반 Step의 초기화 시 신호 및 Async 밖의 무동작을 검증했다. 입력 간 설정 변경과 배치 오류 후 복구, 기본 개별 동기 경로도 유지된다.

전체 회귀는 173개를 실행해 오류 1개·실패 1개·건너뜀 3개였다. 기존 BoxOverlay 예제의 YoloDetectBatch 기대 불일치와 중앙 서버 종료 기대 실패가 남았다. 이후 일반 Step 초기화 범위를 보완하고 최종 Async·YOLO 집중 검증을 다시 실행했다. 마지막 추가 배치 오류 복구 검증도 통과했다.

일관성 분석은 FR-012~015와 SC-006~008의 작업 T029~T033 대응을 확인했으며 미해결 명확화나 구현 차단 충돌이 없었다. 최종 수렴 점검은 기본·배치·신호·CUDA 완료·구성·문서와 기존 Async 계약을 대조하여 추가 작업이 없음을 확인했다. 미작성 헌법 템플릿은 원칙 검증에서 제외했다. 기존 모델 설정과 예제 및 TensorRT 코드는 변경하지 않았다.
## YoloDetect 자체 배치 처리 검증

최신 요청에 따라 중간 YoloDetectBatch 생성·위임을 제거했다. YoloDetect의 자체 배치 반복자는 GPU 입력 복제, 완료 신호, local_yolo.infer 제출과 배치 통계를 직접 처리한다. 기존 YoloDetectBatch 클래스와 사용자 예제 변경은 보존한다.

YoloDetect 22개, Async 28개, 기존 YoloDetectBatch 16개, 공유 작업자 6개를 실행했다. 총 72개에서 실패는 없었고 엔진 파일 부재로 2개를 건너뛰었다. 중간 Step 생성 금지, 설정 변경·간격·배치 실패 복구·통계 귀속, 복사 전후 Async 타임아웃과 늦은 결과 격리, 기본 개별 추론과 기존 공유 작업자 동작을 확인했다.

구현 전 갱신한 직접 경로 테스트의 실패를 확인했다. 일관성 분석에서 FR-016과 T034~T037, SC-006~008의 대응 및 기존 신호 계약을 확인했고 구현 차단 충돌은 없었다. 최종 수렴 점검에서 YoloDetect의 YoloDetectBatch 참조가 없고, 직접 local_yolo 제출·문서·설계·검증이 일치함을 확인했다. 추가 구현 작업은 없다. 이번 변경은 관련 회귀 검증을 수행했으며 전체 중앙 실행 검증을 반복하지 않았다.

## 별도 배치 Step 제거 검증

최신 제거 요청은 과거 별도 API 보존 결정을 대체한다. yolo_detect_batch.py와 클래스·공개 내보내기·별도 문서를 제거했고 예제와 배치 검증은 YoloDetect(..., batch=True)로 통합했다. 이전 별칭은 제공하지 않는다. 사용자 단일 영상 예제의 설정은 보존했다.

구현 전 공개 API 제거 검증의 실패를 확인했다. 통합 배치 15개, YoloDetect 22개, BoxOverlay 5개 검증에서 실패가 없었으며 엔진 파일 부재로 1개를 건너뛰었다. BoxOverlay 검사는 Async 내부 감지 Step을 확인하여 기존 예제 기대 오류를 해소했다.

전체 회귀는 176개 중 172개 통과, 3개 건너뜀, 1개 실패였다. 기존 test_server_exits_after_last_pipeline_disconnects의 중앙 프로세스 종료 기대 실패가 남았다. 실행 코드·예제·공개 문서에서 폐기 API 참조가 없고 제거 확인 테스트만 해당 이름을 사용한다. 변경 파일의 공백 검사도 통과했다.

최종 수렴 점검에서 FR-016과 T038~T041을 코드·예제·공개 내보내기·문서·검증 결과에 대조했다. 통합 배치 경로와 입력 사용 종료 신호는 유지되고 폐기 API 제거가 반영되어 추가 구현 작업은 없다. 중앙 프로세스 종료 실패는 이번 제거 작업 이전에도 발생한 별도 회귀 문제로 기록한다.
## 추론 프레임 간격 이름 변경 검증

YoloDetect는 inference_interval_frame 기본값 1을 사용한다. 두 모드의 간격 선택·정수 검증·실행 중 설정 변경은 유지하며 이전 키는 변경 안내 오류로 거부한다. TensorRTInference 설정은 변경하지 않았다. 예제 YAML과 YOLO·Async·파이프라인·핫스왑 문서 및 README의 YOLO 항목을 갱신했다.

FR-017·SC-009와 T042~T045의 일관성 분석에서 차단 충돌이 없었으며 구현 전 새 설정 검증의 실패를 확인했다. YOLO 23개·배치 15개·Async 28개를 실행해 실패 없이 통과했고 엔진 파일 부재로 1개를 건너뛰었다. 전체 테스트는 반복하지 않았다.
