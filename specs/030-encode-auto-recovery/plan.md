# 구현 계획: 인코더 자동 복구

## 2026-10-16 수명 보장 보완 설계

기존 tests/test_report.py 및 tests/test_hotswap.py의 CUDA 스트림 대역에도 실제 스트림의 synchronize 계약을 반영하고 회귀 검증한다.

FR-007~008, SC-005를 위해 src/pipeworks/embedded/nvidia_decode.py도 수정한다. 새 공개 설정과 의존성은 없다. 복구 가능한 네이티브 예외는 원본 예외 처리 블록을 빠져나온 뒤 문자열만 가진 내부 예외로 변환한다. 호출 래퍼의 bound method와 인수를 지워 이전 세대가 traceback에 남지 않도록 한다. 지원 불가 예외의 기존 전달은 유지한다.

인코더는 공통 정리 함수에서 기존 CUDA 스트림 동기화 → 인코더 해제 → 스트림 해제를 실행한다. 실패, 정상 교체, 중도 종료, 소스·후속 오류에 적용한다. 마지막 제출 입력은 정리까지 보유한다. 실패 인코더의 EndEncode를 재호출하지 않는다.

디코더는 출력 풀 생성 전에도 스트림 동기화를 수행한다. 생산자 종료에도 정리를 실행하며 정상 종료에서는 큐의 잔여 프레임을 버리지 않는다. 기존 풀의 decoder·stream 강참조와 프레임 완료 이벤트는 유지한다. 정상 프레임마다 CPU 동기화를 추가하지 않는다.

검증은 tests/test_nvidia_encode.py와 tests/test_nvidia_decode.py의 약한 참조 및 소멸 로그 시험으로 수행한다. 실제 GPU 시험과 기존 RTSP·프레임 수명 회귀도 실행하고 docs/pipeworks/embedded/nvidia_encode.md 및 nvidia_decode.md를 갱신한다. 헌법은 미작성 양식이며 설계 전후 원칙 위반은 없다. 아래 기존 계획의 정리 동작은 이 보완 설계를 따른다.

**날짜**: 2026-10-15 | **명세**: [spec.md](spec.md)

## 요약

네이티브 인코더 호출에만 복구 예외 경계를 둔다. 오류 프레임과 실패 인코더를 버리고 1초 뒤 도착하는 새 프레임에서 재생성한다. 영상 형식과 입력 스트림 변경을 감지하며 세대 간 패킷 시간 축을 유지한다.

## 기술 배경

- Python 3.11.9, PyNvVideoCodec 2.2.2, torch 2.2.1+cu121, PyAV 18.1.0의 기존 Python 라이브러리 구조를 사용한다.
- 새로운 의존성이나 공개 설정을 추가하지 않는다. 단조 시계 기반 최소 1초 재시도로 생성 폭주를 방지한다.
- 기존 정수 FPS와 패킷 단위 PTS/DTS 증가 계약을 유지한다. process 실행 시작의 FPS와 시간 기준을 모든 인코더 세대가 공유한다.
- unittest의 CPU 대역과 실제 NVIDIA GPU 시험으로 검증한다. 저장소의 기존 Windows 환경에서 수행한다.

## 원칙 확인

헌법은 미작성 양식이므로 검사에서 제외한다. 사용자 지정 한글 문서 및 speckit 단계 순서를 준수한다. 설계 전후 위반 사항은 없다.

## 프로젝트 구조

- src/pipeworks/embedded/nvidia_encode.py: 네이티브 예외 구분, 재시도 상태, 입력 변경 감지, 안전 정리, 헤더 및 로그.
- tests/test_nvidia_encode.py: 정상 출력·오류 복구·반복 실패·형식 변경·종료·오류 분리·GPU 재디코딩 시험.
- docs/pipeworks/embedded/nvidia_encode.md 및 docs/reference/NvidiaEncode.html: 공개 동작 갱신.
- specs/030-encode-auto-recovery/: 명세·조사·설계·계약·검증 안내·작업 목록.

## 구현 단계

1. CreateEncoder, Encode, EndEncode에서 발생하는 RuntimeError와 설치된 PyNvVCException만 내부 복구 예외로 감싼다. PyNvVCExceptionUnsupported는 전파한다. CUDA 범위 진입·종료와 출력 변환·통계·소스 및 후속 오류는 감싸지 않는다.
2. 실패 프레임은 버리고 인코더를 해제한다. 프레임 처리 실패 시 해당 CUDA 스트림 작업 완료를 기다린 후 프레임 수명을 끝낸다. 동기화 자체가 실패하면 복구 불가능한 GPU 오류로 전파한다. 실패한 인코더에 EndEncode를 재호출하지 않는다.
3. 1초 대기 중 프레임을 저장하지 않고 소비한다. 다음 재시도 시 최신 입력으로 재생성하며 성공 프레임 출력에서만 복구 완료를 기록한다.
4. video_stream identity 및 코덱·너비·높이·픽셀 형식·CUDA 스트림 핸들 변경을 감지한다. 정상 인코더 교체 시 잔여 출력은 이전 메타데이터로 전달한 후 해제한다. 세션 설정 FPS와 GPU 번호는 process 시작 시 고정한다.
5. h264/hevc 인코더에 repeatspspps=1을 지정한다. 새 세션의 시작 IDR 및 헤더가 독립적으로 디코딩되는지 실제 GPU에서 확인한다. next_pts 및 time_base는 교체 시 초기화하지 않는다.
6. 중지 시 재시도 없이 종료한다. 정상 입력 소진 시 EndEncode 오류는 경고 후 잔여 출력을 버린다. finally에서 CUDA 스트림보다 먼저 인코더 참조를 해제한다.

## 검증 및 수렴

먼저 실패하는 복구 시험을 작성한다. 구현 후 GPU 출력의 독립 디코딩과 디코더 연계·송출·통계·기본 설정·프레임 해제 회귀 시험을 실행한다. Python 구문 검사와 git diff --check를 수행하고 speckit-converge로 모든 요구사항을 점검한다.
