# TensorRT 추론 검증 안내

가상환경의 CUDA PyTorch로 `.venv/Scripts/python.exe -m unittest discover -s tests -p test_tensor_rt_inference.py`를 실행한다. 임의 이름·단일 및 다중 입력·원시 GPU 값·동적 출력·플러그인·비동기 실패·수명 계약을 확인한다.

실제 검증에는 TensorRT 10.10과 동일 GPU에서 만든 엔진이 필요하다. TensorRT가 설치된 환경에서는 테스트가 작은 GPU 연산 엔진을 생성하고 실행한다. 현재 TensorRT가 없으면 실엔진 검증만 건너뛴다.

클래스명 YAML은 GPU·간격을, 모델 동명 YAML은 timeout·plugins를 설정한다. 초기화가 오래 걸리는 실제 검증에는 충분한 timeout을 임시 파일에 설정한다. 출력 계약은 [추론 계약](contracts/inference.md)을 따른다.

## 2026-10-08 실행 결과

- TensorRT 단계: 12개 중 11개 통과, 실제 TensorRT 패키지 부재로 실엔진 검증 1개 건너뜀.
- 기존 YOLO: 14개 중 13개 통과, 엔진 파일 부재로 1개 건너뜀.
- 기존 배치: 16개 모두 통과.
- 기존 공유 GPU: 6개 중 5개 통과, 엔진 파일 부재로 1개 건너뜀.
- 합계: 48개 중 45개 통과, 3개 조건부 건너뜀. 새 단계는 모의 TensorRT API와 실제 GPU 텐서로 검증했다. 실제 플러그인 포함 엔진의 호환성과 실행은 TensorRT 설치 환경에서 추가 검증이 필요하다.
## 동기 실행 검증

최신 사용자 요청으로 내부 작업자·큐·자체 타임아웃을 제거했다. 동명 YAML은 plugins만 읽으며 timeout은 무시한다. 호출 스레드에서 별도 CUDA 스트림으로 실행하고 GPU 완료 후 반환한다. 연속 입력의 보호 복제는 제거하고 비연속 입력만 연속화한다. 실패는 전파하며 시간 제한·오류 통과는 공통 Async가 담당한다.

FR-020~022와 SC-010의 작업 대응을 분석했고 차단 충돌은 없었다. TensorRT 12개·예제 전후처리 4개·Async 35개·BoxOverlay 5개 검증이 모두 통과했다. 실제 엔진 생성·실행과 제공된 YOLO plan, 호출 스레드·무복제·간격·입력 형식·플러그인 및 Async 초기 로딩 타임아웃을 검증했다. 전체 테스트는 반복하지 않았다. 수렴 점검에서 추가 구현 차이는 없다.
## 배치 연결 검증

TensorRTInference(model_path, batch=True)는 local_tensor_rt에 GPU 입력과 준비 이벤트 및 추론 완료 콜백을 전달한다. 기본 False의 동기 실행은 유지한다. FR-023~024와 SC-011의 일관성을 확인했다. 직접 요청·간격 3·원본 입력 식별·통계 귀속·오류 전파·엄격한 batch 검증을 추가했다.

TensorRT 14개·공유 배치 3개·전후처리 5개 검증이 모두 통과했다. 실제 개별 엔진과 예제 plan을 포함하며 공유 배치 연결 자체는 모의 실행기로 검증했다. 예제의 배치 모드는 변경하지 않았다. 최종 수렴 점검에서 추가 구현 차이는 없다.

## NMS 입력 복제 제거 검증

2026-10-09: 예제 TensorRTPostProcess는 prediction을 직접 NMS에 넘긴다. 원시 출력은 제자리 좌표 변환을 허용하며 후처리 이후 재사용하지 않는다. input.detections만 유지하고 모델 입출력은 정리한다.

명세·명확화·계획·작업 대응을 분석했으며 추가 질문과 차단 충돌은 없었다. 기존 CUDA 결과 검증에 clone 금지 조건을 추가하여 구현 전 prediction.clone()에서 실패함을 확인했다. 제거 후 원시 좌표 변환·NMS 중복 제거·클래스 필터·좌표 복원·신뢰도·이름·빈 결과·모델 버퍼 정리와 BoxOverlay의 원본 영상 표시를 확인했다.

test_tensor_rt_processing 6개, test_box_overlay 5개, test_async 37개, test_frame_release 6개로 총 54개가 모두 통과했다. 제공된 실제 plan의 추론·후처리도 포함한다. git diff --check가 통과했고 FR-025~026·SC-012 및 계획·작업의 수렴 점검에서 남은 구현 작업은 없다. 전체 테스트와 성능 수치 측정은 수행하지 않았다.
