# 구현 계획: 후처리 최적화

## 기술 맥락

Python 3.11, Torch 2.2.1, torchvision 0.17.1, Ultralytics를 유지한다. `examples/step/tensor_rt_post_process.py`의 배치 1·80클래스·축 정렬 박스 후처리를 최적화한다.

## 원칙 확인

헌법은 미작성 템플릿이므로 별도 원칙을 도출하지 않는다. Markdown 한글 작성과 speckit 순서를 준수한다.

## 설계

전체 80클래스 최고 점수를 한 번 계산하고 confidence와 classes를 하나의 마스크로 결합한다. 입력 xywh→xyxy 변환은 유지한다. 후보 전체 84열을 여러 번 압축하는 대신 최종 6열을 한 번 필터링한다. torchvision.ops.nms, 클래스 오프셋 7680, 최대 후보 30000, max_det를 유지한다. N=6은 기존 라이브러리 특례를 그대로 호출한다.

좌표 복원은 x/y 슬라이스에 in-place 연산을 적용하여 고급 인덱싱을 줄인다. 클래스 비교 텐서는 프레임별 생성하여 스트림 간 캐시 동기화를 추가하지 않는다. 완료 대기는 유지한다.

## 검증

`tests/test_tensor_rt_postprocess_optimized.py`에 CPU/CUDA 참조 NMS 비교를 추가한다. 기존 `tests/test_tensor_rt_processing.py`의 오래된 전처리 import를 현재 공개 클래스로 바꿔 기존 통합 검증을 재사용한다. `tools/benchmark_postprocess.py`에서 희소·밀집 점수 입력을 기존 전체 후처리와 비교한다.

## 단계

명세·명확화 → 계획 → 작업 → 읽기 전용 분석 → 구현·검증 → 수렴 검토.
