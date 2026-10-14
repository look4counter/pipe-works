# inference_contract: 전후처리 연결 계약

구현: src/pipeworks/inference_contract.py. 이 모듈은 모델별 영상 전후처리를 구현하지 않고 컨텍스트의 좌표 정보·측정 프로파일·임시 필드 수명을 연결합니다. 일반 앱은 YoloInference와 자신의 전후처리를 조합하고, 보고를 통합하는 사용자 전후처리에서 다음 도우미를 사용할 수 있습니다.

| 함수 | 동작 |
| --- | --- |
| inherited_profile(item) | _inference_profile, _yolo_profile, _tensor_rt_profile 순으로 첫 None 아닌 값 반환 |
| bind_profile(profile, kind) | 기존 구간을 보존하며 실제 backend 종류와 활성 통계 저장소 연결 |
| begin_preprocess(preferred_kind) | 해당 종류 또는 활성 보고 종류에 맞는 Profile 생성. 측정 비활성 시 None |
| pop_profile(item) | 기존 프로파일을 반환하고 세 프로파일 필드 모두 제거 |
| image_transform(item) | image_transform, yolo_transform, tensor_rt_transform 순으로 첫 None 아닌 좌표 정보 반환 |
| clear_model_context(item) | model_input·model_output·model_id와 위 좌표·프로파일 필드를 모두 제거 |

image_transform 함수는 타입 변환이나 좌표 계산을 하지 않습니다. 좌표 정보 객체의 실제 타입과 계산은 사용자 전처리·후처리가 합의해야 합니다. 코어에는 ImageTransform 클래스나 GPU 이미지 리사이즈 구현이 없습니다.

## 권장 데이터 흐름

전처리가 독립 GPU model_input과 필요하면 image_transform을 생성합니다. YoloInference는 model_id·이름별 원시 model_output을 기록하고 상속받은 프로파일을 실제 backend에 연결합니다. 후처리는 모델의 출력 스키마를 해석해 detections 등 앱 결과를 기록한 뒤 임시 필드를 정리합니다. detections·frame·cuda_stream은 clear_model_context가 제거하지 않습니다.

측정에 참여하는 전처리는 begin_preprocess로 받은 값이 None이 아닐 때 _inference_profile에 보관하고, 후처리는 pop_profile로 꺼내 종료 상태에 맞게 finish합니다. 프로파일이 없을 때도 전후처리는 정상 동작해야 합니다. Profile·span의 측정 항목은 [YoloReport](embedded/yolo_report.md)를 따릅니다. 내보낸 모델이 이미 NMS를 포함하면 후처리에서 중복 적용하지 않도록 모델 계약을 확인합니다.

이전 필드명은 읽기 호환용입니다. 새 앱은 image_transform·_inference_profile을 사용합니다. clear_model_context 이후 임시 필드를 읽는 하류를 연결하지 마세요.
