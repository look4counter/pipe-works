# 데이터 모델

새 데이터 개체는 없다. Pipeline의 name, config, batch_server, steps를 그대로 사용한다. batch_server는 대소문자를 구분하는 영문자·숫자·밑줄·하이픈 1~64자이며 기본 production이다.

실행 전이: 호출자 run → 별칭의 중앙 서버 연결 → 직렬화된 파이프라인의 서버 내부 단계 실행 → 응답·정리. batch는 개별 추론과 공유 배치 추론만 선택한다.
