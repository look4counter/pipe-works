# 구현 계획: 추론 입력의 CPU 대기 제거

작성일: 2026-10-10. 명세: [spec.md](spec.md).

## 요약

입력 준비는 텐서와 준비 이벤트를 반환한다. 개별 실행 스트림은 contiguous 이전 wait_event를 등록하고, 배치는 동일 이벤트를 작업자에게 전달한다. 같은 스트림에서도 안전하므로 별도 분기를 추가하지 않는다.

## 기술 환경

Python 3.11.9, PyTorch 2.2.1 CUDA 12.1, TensorRT 10.10, unittest를 사용한다. 대상은 기존 GPU 영상 처리 라이브러리이다. 현재 RTX 4070 Laptop GPU에서 검증 가능하다. 공개 설정과 저장 형식은 유지한다. 성능 목표는 입력 준비 CPU 완료 대기 0회이다.

## 헌장 점검

헌장은 미작성 템플릿이므로 확정 원칙 검사를 생략한다. 저장소의 한글 문서·speckit 절차를 준수한다. 설계 전후 위반 없다.

## 프로젝트 구조와 단계

- src/pipeworks/embedded/tensor_rt_inference.py: 입력과 이벤트 반환, 개별 소비 스트림 대기, 배치 중복 이벤트 제거.
- src/pipeworks/local_tensor_rt.py: torch.cat 이전 요청 이벤트를 소비 스트림으로 기다림.
- tests/test_tensor_rt_inference.py, tests/test_local_tensor_rt.py: CPU 입력 대기 금지와 실제 지연 GPU 입력의 결과 일치 검증.
- docs/pipeworks/embedded/tensor_rt_inference.md: 입력 순서 및 완료 계약 갱신.

## 설계와 제약

[연구](research.md), [데이터 모델](data-model.md), [계약](contracts/inference.md), [검증 안내](quickstart.md)를 따른다.
입력 참조는 기존 최종 완료 대기까지 유지한다. 개별 이벤트 등록은 기존 try/finally 안에 두어 오류 시에도 정리한다. 배치 실패도 기존 스트림 정리 후 요청 참조를 해제한다.
추론·후처리·CudaAsync의 최종 완료 동기화는 변경하지 않는다.
