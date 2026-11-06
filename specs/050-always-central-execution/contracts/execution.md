# 실행 계약

Pipeline(name, *, config, batch_server="production") 및 run()의 인자는 유지한다. run은 모든 단계 구성을 지정한 중앙 서버로 전달한다. 실패 시 로컬 실행으로 대체하지 않는다.

YoloInference(batch=False)는 중앙 서버 내부에서도 공유 배치 워커를 호출하지 않는다. batch=True인 단계만 기존 공유 배치 워커를 사용한다. 실행 위치를 이유로 batch 값을 변경하지 않는다.

서버는 전달된 파이프라인에 _run_local(stop)을 호출한다. 종료 감지·로그·오류 전달·유휴 종료 정책은 기존 경로를 사용한다.
