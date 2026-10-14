# file_watch: 프로세스별 공유 파일 감시

구현: src/pipeworks/file_watch.py. Pipeline 설정과 Hotswap 코드 변경 감시의 내부 기반입니다. 일반 앱에서는 파일을 저장하면 Pipeline이 감지하므로 직접 구독할 필요가 없습니다.

## 객체와 메서드

| API | 동작 |
| --- | --- |
| FileSnapshot(source, digest) | 불변 데이터. source는 파일 bytes, digest는 SHA-256 16진 문자열 |
| FileSubscription(path, *, service=None) | 생성 시 절대경로로 정규화. 실제 감시는 최초 snapshot에서 지연 등록 |
| subscription.snapshot(*, force=False) | 현재 스냅샷 반환. force=True이면 내용 강제 재검사 |
| subscription.close() | 현재 구독 해제. 이후 snapshot 호출은 다시 구독 가능 |

service는 내부 주입용입니다. FileSubscription은 문맥 관리자 API를 제공하지 않으므로 직접 사용할 때 try/finally에서 close합니다. 읽기 오류는 호출자에게 전달하고 변경 표시를 유지해 복구 후 재시도합니다.

## 감시와 재검사

동일 프로세스의 경로·부모 디렉터리 감시와 내용 스냅샷을 공유합니다. 생성·수정·삭제·이동 알림은 변경 표시만 남기고 실제 파일 읽기와 해시는 snapshot 요청에서 계산합니다. 알림이 정상이어도 30초 간격으로 내용을 확인하고 감시 장애 시 0.5초 간격 재검사·재등록을 시도합니다. 수정 시각·파일 크기가 같아도 재검사 시 내용으로 판단합니다.

스냅샷 호출자의 처리 간격도 적용되므로 저장 즉시 새 코드가 실행된다는 보장은 없습니다. 마지막 구독이 끝나면 감시기를 정리하고 프로세스 종료 정리도 등록합니다. 직렬화 시 파일 경로만 전달하며 다른 프로세스에서 서비스·스레드를 다시 만듭니다. 공유 서비스·observer·_Entry 등 밑줄 이름은 앱의 확장 지점이 아닙니다.

[Pipeline](pipeline.md)과 [Hotswap](hotswap.md)의 설정 실패·코드 교체 정책을 함께 확인하세요.
