# 실행 문제 해결

| 증상 | 확인할 항목 |
| --- | --- |
| pipeworks를 import할 수 없음 | 실행 Python과 SDK 설치 환경이 같은지, 직접 src 참조 시 PYTHONPATH가 src를 가리키는지 확인 |
| 사용자 Step 또는 backend import 실패 | 앱 패키지·의존 도우미를 배포하고 중앙 프로세스의 Python 환경·PYTHONPATH에서도 import 가능하게 구성 |
| 설정 파일 FileNotFoundError | Pipeline은 생성 시 YAML을 읽음. 앱 파일 기준 절대경로와 실제 파일 존재 확인 |
| 모델을 찾지 못함 | 모델 경로를 앱의 __file__ 기준 절대경로로 전달. 중앙 프로세스 작업 디렉터리에 의존하지 않기 |
| YAML 형식 오류 | 최상위와 Step 섹션은 매핑. 빈 설정은 {}. 클래스명 대소문자 확인 |
| backend 필수 인자 오류 | YoloInference 생성자에서 Backend 또는 모듈:클래스 문자열을 명시 |
| TorchScript 로딩 실패 | 일반 .pt 체크포인트와 TorchScript는 다름. 실제 모델 형식과 backend 확인 |
| CPU 또는 다른 GPU 텐서 오류 | model_input·출력·cuda_stream의 GPU를 gpu_id에 맞추고 GPU 데이터의 item·bool 등 CPU 읽기 제거 |
| 공유 배치 축 오류 | 요청 입력 첫 축은 1, 결합 모델의 모든 출력 첫 축은 요청 수여야 함 |
| 모델 YAML 오류 | 모델과 같은 디렉터리의 동명 .yml에 max_batch_wait_ms 사용. 비 TensorRT 파일은 max_batch_size·max_batch_wait_ms를 모두 명시 |
| 설정 변경 후 모델·플러그인이 그대로임 | 모델 YAML과 작업자는 자동 재로드하지 않음. 해당 실행 프로세스 재시작 |
| 비동기 결과가 간헐적으로 없음 | busy·timeout과 안전한 프레임 폐기 정책 확인. CudaAsync 기한과 원본 사용 종료 신호 확인 |
| 디코더가 멈추거나 잠금 버퍼가 고갈됨 | 외부 코드가 이전 frame·별칭 텐서를 계속 보관하는지 확인하고 사용이 끝난 참조 해제 |
| 중앙 전달 TypeError | 생성자에 열린 연결·GPU 모델·잠금 등 직렬화하기 어려운 상태가 있는지 확인하고 process에서 지연 생성 |
| Windows SID·named pipe 관련 오류 | 현재 main 모듈은 Windows 구현. whoami 실행, 같은 사용자·설치·Python 환경 확인 |
| 코드 수정이 바로 반영되지 않음 | 처리 경계·감시 간격과 로그 확인. 내장 Step과 가져온 공통 라이브러리는 자동 코드 교체 대상 아님 |

중앙 연결이 끊기면 run은 RuntimeError를 전달할 수 있습니다. 클라이언트 연결 종료·heartbeat 중단은 서버의 중단 신호로 이어지지만 이미 실행 중인 블로킹 수신·GPU 작업을 즉시 취소하지는 않습니다. 상류가 계속 소비하는 Sink 뒤의 단계는 컨텍스트를 받지 못하므로 사용자 결과 처리는 Sink 앞에 둡니다.

[설치와 앱 실행](getting_started.md), [설정](configuration.md), [중앙 실행](main.md), [Step 목록](README.md)을 참고하세요.
