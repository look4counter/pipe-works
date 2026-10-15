# 내부 통신 계약

central-v20 주소에서 새 요청 봉투와 (log, 로그 필드 dict), (ok, None), (error, 문자열) 응답을 사용한다. 기존 하트비트와 ping/pong은 유지한다.

로거 이름과 수준은 원래 값을 유지하며 출력 어댑터는 pipeworks.user_output/DEBUG를 사용한다. 로그에 pipeworks_pipeline과 pipeworks_execution_id를 추가한다. print의 개행은 로그 메시지 경계이며 최종 개행과 접두사는 호출자 포맷터가 결정한다.

정책은 요청 시 캡처하며 수신 단계에도 현재 호출자 로그 설정을 적용한다. 서버에서 이후 임의로 명시 수준이나 핸들러를 재설정하면 중앙 준비 정책을 우회할 수 있으므로 호출자에서 설정한다. 네이티브 stdout·stderr와 문맥 없는 사용자 스레드는 범위 밖이다.
