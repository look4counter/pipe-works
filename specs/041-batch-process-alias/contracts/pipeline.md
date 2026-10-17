# 생성자 계약

Pipeline(name, *, config, batch_process="production")

별칭은 대소문자를 구분하는 영문자·숫자·밑줄·하이픈 1~64자다. 비문자열은 TypeError, 잘못된 문자열은 ValueError다. development는 더 이상 받지 않는다. run()의 인자는 변경하지 않는다. CLI --server-group은 유지한다.
