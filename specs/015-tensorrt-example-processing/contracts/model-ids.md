# 모델 ID별 탐지 계약

YoloDetect(model_path, id=None)도 같은 기본값·검증·YAML 우선순위를 적용한다. 개별/배치/건너뜀/오류 모두 현재 detections[id]만 교체하고 다른 결과를 보존한다. 사전을 복사한 후 입력 시작 ID에 저장하여 비동기 공유 사전과 설정 변경의 영향을 차단한다. 개별 오류는 전파하고 배치 오류는 기존처럼 통과한다. local_yolo.infer의 직접 반환 계약은 바꾸지 않는다.

TensorRTInference(model_path, id=None)는 기본 모델 파일명 또는 지정한 비어 있지 않은 문자열을 ID로 사용한다. YAML id가 우선하며 null은 파일명, 제거는 생성자 값이다. ID는 엔진 공유 설정에 영향을 주지 않는다.

TensorRT 입력은 model_id를 전달받는다. 후처리는 detections[model_id]에 boxes·names·orig_shape 결과를 넣고 다른 키는 유지한다. 같은 키는 교체한다. 누락 또는 오류는 현재 키에 None을 넣는다. model_id가 없고 출력도 없으면 빈 사전 또는 기존 사전을 유지하며 출력이 있으면 오류다. 후처리에서 사전을 복사하여 원본 컨텍스트의 공유 사전은 수정하지 않는다. 임시 model_id는 GPU 완료 확인 뒤 정리한다. YOLO는 내부 후처리까지 완료하므로 임시 model_id 없이 결과를 저장한다.

BoxOverlay의 YAML id는 하나의 ID를 선택한다. null이면 전체다. keep_previous는 ID별 적용하고 빈 탐지 결과는 해당 캐시를 지운다. 기존 단일 YOLO 결과 객체는 id 선택 없이 표시한다. 모든 모델 추론 후 Overlay를 실행한다. 성능 보고는 탐지 사전과 독립이고 실제 DB 저장 기능은 이번 범위가 아니다.
