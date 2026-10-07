# Main: 중앙 스트림 프로세싱

파이프라인을 별도의 중앙 프로세스에서 실행합니다 (내부용).

**파일 위치:** `src/pipeworks/main.py`  
**용도**: 내부 구현 (사용자는 직접 사용 안 함)

---

## 📚 개요

- 파이프라인을 중앙 프로세스에서 관리
- `pipeline.run()` 호출 시 자동으로 사용됨
- Named pipe를 통한 프로세스 간 통신

---

## 🔧 내부 동작

```
pipeline.run()
    ↓
run_remote() 호출
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
