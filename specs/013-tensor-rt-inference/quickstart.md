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
