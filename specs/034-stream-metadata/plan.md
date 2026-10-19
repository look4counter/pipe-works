# 구현 계획: 비디오 스트림 수명 분리

## 개요

Python 3.11.9, PyAV 18.1.0, PyNvVideoCodec 2.2.2를 유지한다. 새 의존성은 없다.
수신 연결에서 불변 VideoStreamInfo와 CodecInfo를 한 번 만들고 기존 video_stream 필드로 공유한다.

## 기술 맥락

- 저장소: src/pipeworks, tests, docs/pipeworks.
- 입력 메타데이터: 코덱 이름·크기·extradata·픽셀 형식·시간 기준·평균 프레임률·연결 식별자.
- 복구: 디코더·인코더의 객체 교체 감지는 연결마다 새 메타데이터를 생성하므로 보존한다. 송출 키에 연결 식별자를 추가한다.
- 출력 메타데이터: 인코더 생성 세대별로 최초 출력에서 실제 Annex B SPS/PPS/VPS만 추출한다. 입력 extradata는 재사용하지 않는다. 반복 헤더 옵션을 유지한다.
- 송출: 임시 로컬 출력 템플릿을 생성하여 출력 스트림의 템플릿 초기화 상태를 만들고, 값으로 보관한 코덱 설정과 extradata를 출력 codec_context에 설정한다. 임시 컨테이너는 함수 안에서 닫는다. 원본 수신 스트림은 사용하지 않는다.
- 성능: 입력 연결당 1회 복사, 인코더 세대당 최초 출력 1회 헤더 추출, 송출 연결당 1회 초기화. 매 프레임 영상 복사는 없다.

## 헌법 검토

헌법은 미작성 템플릿이므로 규범 검사는 생략한다. AGENTS.md의 한글 문서와 전체 speckit 순서를 준수한다.

## 단계 및 파일

1. src/pipeworks/video.py에 불변 값 모델과 복사·송출 복원·인코더 헤더 도우미를 작성한다.
2. rtsp_source.py에서 연결마다 복사한다. nvidia_decode.py는 기존 값 접근과 교체 감지를 유지한다.
3. nvidia_encode.py에서 출력 세대별 메타데이터와 지연 패킷 계약을 유지한다.
4. rtsp_publish.py에서 메타데이터로 출력 생성 및 연결 식별자를 적용한다.
5. tests/test_video.py 및 기존 소스·인코더·송출 테스트에 회귀 검증을 추가하고 문서 계약을 갱신한다.

## 검증

실제 PyAV의 h264/hevc 파일 송출·재디코딩으로 헤더 보존을 검증한다. 컨테이너 종료 후 메타데이터 접근과 1,000개 패킷 공유를 검증한다. 관련 unittest와 전체 회귀 검사를 실행한다. 실제 GPU·RTSP 실험은 장비 가용성에 따른 한계를 기록한다.

## 2026-10-20 생성 시 검증 제거

FR-008에 따라 src/pipeworks/video.py의 CodecInfo.__post_init__에서 이름·너비·높이 검사와 ValueError만 제거한다. extradata 변환과 불변성은 유지한다. tests/test_video.py의 기존 거부 검증을 빈 이름·0 및 음수 크기의 원본 값 보존과 스트림 복사 검증으로 변경한다. 비디오·RTSP 소스·송출 테스트를 실행한다. 새 의존성이나 복구 정책은 추가하지 않는다. 헌법은 미작성 템플릿이며 한글 문서와 전체 speckit 순서를 준수한다.

## RTSP 메타정보 복구 설계

Python·PyAV와 기존 의존성을 유지한다. src/pipeworks/embedded/rtsp_source.py에 입력 연결 전용 메타정보 읽기 도우미와 내부 복구 신호를 둔다. 원본 이름·크기의 형식을 먼저 검사하고 VideoStreamInfo.from_stream을 한 번 호출한 뒤 시간 기준·평균 프레임률·인덱스를 확인한다. 메타정보 읽기·변환의 AttributeError, TypeError, ValueError, OverflowError, ZeroDivisionError만 이 경계에서 복구 신호로 바꾼다. 비디오 스트림 부재도 같은 신호다. CodecInfo의 생성 허용 계약은 유지한다.

RTSPSource.process는 내부 신호를 잡아 수신 실패와 경고를 기록하고 finally로 컨테이너를 닫는다. continue로 공통 대기를 건너뛰지 않고 기존 취소 가능한 대기 경로를 재사용한다. 메타정보 오류는 reconnect=False에도 재시도한다. demux와 후속 처리의 무관한 예외는 잡지 않는다. 정상 복사·공유와 연결 식별자는 기존대로 유지한다. 픽셀 형식·GPU 코덱 지원 목록의 제한은 추가하지 않는다.

tests/test_rtsp_source.py에 오류 종류별 복구, 연속 실패와 정상 재개, 닫힘·대기 순서, 비디오 스트림 부재, 중단·취소, 무관한 예외 전파 검증을 추가한다. 기존 비디오·소스·송출·디코더 회귀를 실행한다. docs/pipeworks/embedded/rtsp_source.md와 데이터·호출 계약 및 검증 결과를 동기화한다. 헌법은 미작성 템플릿이며 구현 전후 문서 규칙과 필수 절차를 재검토한다.
