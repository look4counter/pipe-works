# 실행 계약

Pipeline.run()의 인자는 바뀌지 않는다. Batch 추론이 없으면 _run_local()을 한 번 호출하고, 있으면 run_remote(self)를 한 번 호출한다. 중앙 서버도 기존 _run_local(stop)를 계속 호출한다. 개발 설정은 중앙 실행일 때만 그룹을 고른다. 출력과 자원 정리는 각 기존 실행기에 맡긴다.
