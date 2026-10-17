# 생성자 계약

`Pipeline(name, *, config, batch_server="production")`

이전 batch_process 인자는 TypeError로 거부한다.
새 속성 batch_server는 직렬화 시 보존되며 run_remote에서 server_group으로 전달된다.
