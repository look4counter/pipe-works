# 구현 계획: 단계별 YAML 설정과 동적 컨텍스트

**기준**: [명세](spec.md)

## 후속 설계: RTSP 제한 시간 밀리초 통일

Python 3.11.9, 기존 PyAV와 unittest를 사용하며 새 의존성은 없다. 헌장은 미작성 템플릿이므로 원칙 검증을 생략한다. 문서는 한글로 작성하고 기존 사용자 변경을 보존한다.

`rtsp_source.py`와 `rtsp_publish.py`의 구성 속성을 `timeout_ms`로 바꾸고 기본값을 5000으로 둔다. 속성을 저장하기 전에 유한한 0 이상의 숫자인지 검증한다. 이전 `timeout`이 있으면 오류를 발생시킨다. 기존 파이프라인 설정 갱신과 복구 경로는 유지한다.

수신의 `av.open(timeout=...)`에는 `timeout_ms / 1000`을 연결·읽기 튜플로 전달한다. 송출은 FFmpeg 옵션 이름 `timeout`을 그대로 두고 `int(timeout_ms * 1000)`의 마이크로초 문자열을 전달한다. 패킷 처리·재연결 로직과 재연결 간격의 초 단위는 바꾸지 않는다.

테스트를 먼저 작성해 기본값·0·250·1250.5ms와 이전 이름·잘못된 값의 처리를 검증한다. `examples/config/stream.yml`의 두 섹션, README와 RTSP·파이프라인 안내, 기존 RTSP 명세의 해당 계약을 갱신한다. 모델 YAML의 timeout과 FFmpeg 옵션 이름은 변경 대상이 아니다.

검증 파일은 `tests/test_rtsp_source.py`, `tests/test_rtsp_publish.py`, `tests/test_pipeline_config.py`이며 전체 회귀 후 수렴 점검한다. 설계 후 미해결 질문이나 원칙 충돌은 없다.

## 현재 구성

`Pipeline.__init__`은 YAML을 읽고 모든 섹션의 매핑 구조를 검증한 뒤 최상위 설정을 `SimpleNamespace`로 보관한다. `Pipeline.step()`은 원래 단계 클래스명으로 섹션을 찾고 속성형 설정을 `configure()`에 전달한다. 사용자 정의 단계는 `Hotswap`으로 감싸며 설정을 래퍼에 보관해 재시작 시 재적용한다. 내장 단계는 직접 등록한다.

`Step`의 기본 `configure()`는 아무 동작도 하지 않는다. 실제 단계가 필요한 값을 개별 속성으로 저장한다. `PipelineContext`는 필드 없는 동적 객체다. 디코더와 인코더는 출력마다 새 컨텍스트를 만든다.

`RTSPSource`는 전송 방식·제한 시간·재연결 정책을 개별 속성에 저장한다. 중앙 프로세스가 전달한 중단 이벤트가 있으면 재연결 대기에도 이를 사용한다.

## 검증

설정 구조·전달은 `tests/test_pipeline_config.py`, 동적 컨텍스트는 `tests/test_pipeline_context.py`, 재설정은 `tests/test_hotswap.py`, RTSP 동작은 `tests/test_rtsp_source.py`에서 확인한다. 동일 객체 전달과 새 객체 생성의 차이는 T006에서 검증했다.

## 실행 중 YAML 재적용 설계

1. `Pipeline`에 설정 경로를 보존한다. 실행 프로세스의 설정 감시자는 파일 내용 해시가 달라졌을 때만 YAML을 읽고 구조를 검증한다. 실패한 파일은 기록하고 마지막 정상 설정을 유지한다.
2. 단계별 감시 요청은 클래스명 섹션의 실제 값 차이만 반환한다. 다른 섹션 변경과 내용이 같은 저장은 현재 단계에 영향을 주지 않는다.
3. 실행 중 사용자 Step의 기존 `Hotswap`에 설정 공급자를 연결한다. 내장 Step은 등록 목록을 변경하지 않고 실행 경로에서만 코드 감시를 끈 래퍼로 감싸 설정 확인 경계를 제공한다. `Tap`는 내부 Step의 감시자에 공급자를 연결한다.
4. 설정 변경 시 기존 인스턴스의 최상위 속성을 보관하고 해당 인스턴스의 `configure()`를 실행한다. 성공하면 처리 반복자를 유지하고, 실패하면 보관한 속성을 복원해 이전 설정을 유지한다. 코드 변경이 동시에 발생하면 설정 적용 후 기존 코드 교체 계약을 따른다.
5. 소스는 출력 경계, 입력 단계는 다음 입력 요청에서 설정을 확인한다. 설정 변경만으로 디코더·인코더·송출 생성기를 종료하지 않는다. 현재 열린 자원이 생성 시점에 읽은 값은 자연스러운 자원 재생성 때 적용한다.
6. 테스트에서는 사용자 Step, 내장 Step, `Tap`, 소스, 잘못된 YAML, 설정 오류, 중앙 실행과 인스턴스·처리 반복자 식별자 유지를 확인한다.
# 후속 계획: 재연결 간격 밀리초 통일

RTSPSource와 RTSPPublish는 reconnect_interval_ms 기본값 3000을 저장한다. timeout_ms와 같은 유한한 비음수 숫자 검증을 적용하며 이전 reconnect_interval 키는 오류로 거부한다. 수신 time.sleep과 stop.wait, 송출 연결 실패와 mux 실패의 retry_at 계산에서는 1000으로 나누어 초로 변환한다. 수신 로그도 밀리초로 표시한다. 다른 재연결 정책은 보존한다.

tests/test_rtsp_source.py는 기본값·0·소수 대기와 중단 이벤트, test_rtsp_publish.py는 연결 및 송신 실패 후 250ms 경계와 잘못된 설정을 검증한다. test_pipeline_config.py의 구성 예제를 밀리초로 옮긴다. examples/config/stream.yml, README.md, docs/pipeworks/pipeline.md 및 두 RTSP 문서는 이름과 수치를 함께 환산한다. 기존 RTSP 데이터 계약도 갱신한다. 관련 테스트만 실행하며 코드·명세·작업의 수렴을 확인한다.
