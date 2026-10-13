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
