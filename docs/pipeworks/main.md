# Main: 중앙 스트림 프로세싱

Batch 추론이 포함된 파이프라인을 별도의 중앙 프로세스에서 실행합니다 (내부용).

**파일 위치:** `src/pipeworks/main.py`  
**용도**: 내부 구현 (사용자는 직접 사용 안 함)

---

## 📚 개요

- 파이프라인을 중앙 프로세스에서 관리
- `pipeline.run()` 호출 시 Batch 추론이 있으면 자동으로 사용됨
- Named pipe를 통한 프로세스 간 통신

## 운영·개발 중앙 프로세스 분리

```python
production_pipeline = Pipeline("production", config=Path("stream.yml"))
development_pipeline = Pipeline(
    "development", config=Path("stream.yml"), development=True
)
production_pipeline.run()
development_pipeline.run()
```

같은 설치·Windows 사용자·실행 모드의 Batch 파이프라인은 하나의 중앙 프로세스를 공유합니다. 운영과 개발은 별도 프로세스와 연결 주소·시작 잠금을 사용합니다. Pipeline 생성자의 `development` 기본값은 `False`이며 운영용 프로세스를 선택합니다. `True`는 개발용 프로세스를 선택합니다. bool 이외의 값은 생성 시 오류로 거부합니다.

선택 그룹은 필요할 때 자동 시작하고 마지막 연결 종료 후 유휴 상태가 되면 자동 종료합니다. 개발 그룹의 종료는 운영 그룹의 연결과 작업자를 종료하지 않습니다. `development`는 생성자 옵션이며 YAML 실시간 변경 대상이 아닙니다. `run()`에는 선택 인자를 전달하지 않습니다.

`YoloInference(batch=True)`가 하나라도 있으면 영상의 Step과 GPU 추론을 모두 선택한 중앙 프로세스에서 실행합니다. 래퍼 내부도 검사하며 일반 추론과 Batch 추론이 섞여 있어도 전체 파이프라인을 중앙에서 실행합니다. Batch 추론이 없는 파이프라인은 호출자 프로세스에서 실행합니다. 서로 다른 그룹은 모델 배치·엔진 세션을 공유하지 않으므로 같은 모델도 그룹마다 로드하여 GPU 메모리를 추가로 사용합니다. 같은 GPU의 연산·메모리 자원과 드라이버 리셋·장치 전체 장애는 공유합니다.

내부 서버를 직접 실행할 때도 그룹을 지정할 수 있습니다.

```powershell
python -m pipeworks.main --server-group development
```

---

## 🔧 내부 동작

```
pipeline.run()
    ↓
Batch 추론 존재 여부 검사
    ├─ 없음 → 호출자에서 _run_local() 실행
    └─ 있음 → run_remote() 호출
    ↓
cloudpickle로 Pipeline 직렬화
    ↓
named pipe를 통해 중앙 프로세스로 전송
    ↓
main.py가 수신 후 실행
    ↓
결과 반환
```

---

## 💡 TIP

일반 사용자는 이 모듈을 직접 사용할 필요가 없습니다.  
`Pipeline.run()` 메서드를 사용하면 내부적으로 처리됩니다.

---

## 🔗 관련 문서

- [Pipeline](pipeline.md): 파이프라인 인터페이스
- [Hotswap](hotswap.md): 실행 중 재로드

## 배포와 사용자 앱의 조건

현재 구현은 Windows 전용 경로를 사용합니다. import 시 whoami로 사용자 SID를 읽고 AF_PIPE·msvcrt·Windows 프로세스 생성 플래그를 사용합니다. 같은 설치 경로·사용자·프로토콜·그룹이 중앙 프로세스 공유 범위를 결정합니다. 일반 앱은 serve나 run_remote를 직접 호출하지 않고 Pipeline.run을 사용합니다.

중앙 프로세스는 클라이언트와 같은 sys.executable의 pythonw.exe가 있으면 그것으로, 없으면 sys.executable로 시작합니다. 시작 시 호출자의 환경과 작업 디렉터리를 상속하지만 이미 실행 중인 서버의 환경은 후속 앱에 맞춰 변경하지 않습니다. 모델·설정은 절대경로를 사용하고 사용자 backend·동적 import 모듈은 서버에서도 가져올 수 있게 설치하거나 최초 시작 전에 PYTHONPATH를 지정합니다.

사용자 Step과 메서드 소유 모듈은 cloudpickle의 값 직렬화로 전달을 시도합니다. 임의 외부 의존성과 파일까지 자동 배포하는 것은 아닙니다. 생성 시 열린 GPU·네트워크 자원 대신 설정을 보관하고 process에서 자원을 준비합니다. stdout 출력은 클라이언트로 전달하지만 모든 stderr·외부 라이브러리 로그까지 같은 방식으로 전달된다는 뜻은 아닙니다.

클라이언트는 약 0.25초마다 heartbeat를 보내고 서버는 약 2초 동안 확인하지 못하거나 연결이 끊기면 중단 신호를 설정합니다. 마지막 실행 연결 종료 후 약 1초 유휴 상태이면 서버가 종료되어 모델 작업자도 사라집니다. 실제 블로킹 호출·GPU 작업 정리 시간은 추가될 수 있습니다. 결과는 완료 상태와 출력 메시지이며 프레임 반환 API가 아닙니다.

서버 그룹 내부 검증은 영문자·숫자·밑줄·하이픈의 1~64자 문자열을 허용하지만 Pipeline은 production 또는 development 두 그룹만 선택합니다. 예제의 production.run과 development.run은 각각 블로킹이므로 연속 호출하면 첫 실행이 끝난 뒤 다음 실행을 시작합니다.

[앱 실행 절차](getting_started.md), [설정과 경로](configuration.md), [공유 모델 작업자](local_yolo_inference.md)를 참고하세요.
