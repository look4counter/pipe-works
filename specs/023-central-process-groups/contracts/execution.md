# 실행 계약

- Pipeline(name, *, config, development: bool=False)는 생성 시 bool을 검증하고 development 상태를 보관한다.
- Pipeline.run()과 run_remote(pipeline)는 선택 옵션을 받지 않고 저장된 모드로 실행한다.
- False와 생략은 내부 production 그룹, True는 내부 development 그룹으로 연결한다.
- 정수·문자열·None은 생성 시 TypeError로 거부한다. 모드 상태는 직렬화 후 유지한다.
- 서버 자동 시작과 직접 실행 명령은 pythonw -m pipeworks.main --server-group GROUP이다.
- 운영 모드는 기존 주소·잠금을 사용하고 개발 모드는 별도 주소·잠금을 사용한다.
- 내부 서버 함수의 그룹 이름은 기반 구현이며 Pipeline 공개 옵션이 아니다.
- 그룹 간 모델 배치·엔진 세션을 공유하지 않는다. batch=False도 선택한 중앙 서버에서 실행한다.
- 출력·오류 전달, 연결 종료와 유휴 종료의 기존 계약을 유지한다.
- 프로세스 충돌을 격리하지만 같은 GPU의 자원·장치 장애는 공유한다.
