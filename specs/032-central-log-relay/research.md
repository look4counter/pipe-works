# 조사: 로그 중계

## 실행별 수준

결정: 호출자의 root와 명시적 named logger 수준·disabled 및 logging.disable 기준을 요청에 담는다. 서버의 로그 생성은 개방하고 실행 route별로 필터한다.
근거: 요청마다 전역 수준을 변경하면 동시 파이프라인끼리 간섭한다. 독립 읽기 전용 설계 검토에서도 root만 DEBUG로 낮추면 명시 수준·비전파가 차단하는 점을 확인했다.
대안: 중앙의 단일 global level을 호출자에 맞춰 계속 변경하는 방식은 제외한다.

## 문맥과 재귀

결정: ContextVar route와 기존 output writer 전달을 결합한다. 전송 오류는 stop만 설정하고 재로깅하지 않는다. 수신 기록에는 중계 방지 마커를 넣는다.
근거: CudaAsync의 예외 기록은 request.context.run 밖이므로 worker 전체의 문맥 전달이 필요하다. 독립 검토에서 중첩 범위 복원과 마지막 부분 줄 처리도 확인했다.

## 직렬화와 호환

결정: 원본 traceback이나 임의 객체를 pickle로 전송하지 않고 메시지와 예외 문자열 및 안전한 필드만 담는다. print는 줄 단위 DEBUG로 변환한다.
근거: logging 인자·extra는 비직렬화 객체나 GPU 자원을 포함할 수 있다. print의 stdout 재출력을 유지하면 레벨 제어가 불가능하다.
대안: print 제거는 기존 사용자 Step 호환성을 깨므로 제외한다. 기존 Python 표준 logging 사용 범위에서 해결되므로 외부 기술 조사는 필요 없다.
