# 구현 계획

[명세](spec.md)에 따라 Python NvidiaEncode에 옵션을 추가한다. 기존 PyAV·PyTorch·PyNvVideoCodec을 사용한다.

## 설계

B프레임은 0이다. 입력 pts·time_base·duration을 검증하고 숫자 튜플만 deque에 저장한다. 비어 있지 않은 출력당 하나씩 소비하여 지연·종료 출력에 대응한다. 세션 해제 시 큐를 비운다. 초과 출력은 폐기한다. 입력 객체와 GPU 프레임은 큐에 보관하지 않는다.

출력 메타데이터의 시간 기준은 패킷에 맞추고 average_rate는 설정 fps로 둔다. 시간 기준이 변경되면 새 메타데이터를 만든다.

## 구조와 순서

1. tests/test_nvidia_encode.py에 원본 시간·누락·지연·복구·설정 검증을 추가한다.
2. src/pipeworks/embedded/nvidia_encode.py에 옵션·검증·큐·메타데이터를 구현한다.
3. docs/pipeworks/embedded/nvidia_encode.md와 docs/reference/NvidiaEncode.html을 갱신한다.
4. 인코더·설정·송출 회귀 검사 후 수렴 점검을 한다.

## 헌장과 제약

헌장은 미작성 템플릿이다. 한글 문서와 speckit 절차를 준수하며 설계 전후 위반은 없다. 현재 환경에서 CUDA와 실제 GPU 사용이 가능함을 확인했으므로 빌드 도구와 개발 의존성이 확보되면 실제 GPU를 검증한다. 외부 RTSP 서버 검증은 별도다.

## 중복·역행 송출 폐기 변경

src/pipeworks/embedded/rtsp_publish.py의 DTS 비교는 유지하고 보정 분기를 continue로 교체한다. 마지막 성공 DTS는 실제 송신 성공 뒤에만 갱신한다. 폐기는 연결 오류가 아니므로 재연결이나 실패 지표를 기록하지 않는다. 기존 DTS 누락 보완은 유지하며 PTS만 비교해 정상 재정렬 영상을 버리지 않는다. tests/test_rtsp_publish.py에 같은 시간 기준의 중복·역행, 서로 다른 시간 기준, 정상 간격, PTS 재정렬 및 연결 유지 검증을 추가한다. 기존 송신 실패 테스트의 반복 패킷 기대값을 새 정책에 맞춘다. docs/pipeworks/embedded/rtsp_publish.md와 nvidia_encode.md 및 docs/reference/NvidiaEncode.html의 기존 보정 문구를 갱신한다. 바인딩 wheel 재빌드는 필요 없다.

## 바인딩 빌드와 무복사 전달 확장

tools/patches에 최소 C++ 바인딩 패치를 보관한다. tools/build_pynvvideocodec.py는 공식 ZIP의 고정 해시를 확인하고 build 아래 별도 소스 작업 디렉터리에 안전하게 추출하여 패치를 적용한다. 메타데이터와 모듈 버전을 2.2.2+pipeworks.1로 변경한다. 원본 ZIP과 현재 설치 패키지는 수정하지 않는다. 준비 전용 모드와 CMake 인자 전달 및 로컬 개발 의존성 경로를 제공한다. Windows용 PowerShell 래퍼로 빌드 진입점을 제공한다.

GetLockedFrameWithPTS는 int64_t timestamp를 선언하고 dec->GetLockedFrame(&timestamp)를 한 번 호출하여 (포인터, PTS)를 반환한다. 빈 출력 호출은 예외로 처리한다. 기존 GetLockedFrame·UnlockFrame은 변경하지 않는다.

NvidiaDecode의 _DecoderBuffers.acquire가 새 API를 우선 사용하여 버퍼 소유자에 pts를 붙인다. 새 API가 없는 모의·공식 디코더는 기존 잠금 API로 동작한다. 각 디코더 세션의 time_base는 첫 유효 입력의 packet.time_base 또는 video_stream.time_base를 사용하고 이후 패킷 PTS를 그 단위로 환산한다. 컨텍스트 pts는 오직 실제 디코딩 출력 API의 값이며 미제공·미정 시각은 None이다. API 없는 기본 동작은 유지한다.

수정 wheel은 기본 프로젝트 설치를 강제 변경하지 않고 requirements-pynvvideocodec.txt의 정확한 로컬 버전과 wheelhouse 설치 명령으로 선택한다. requirements-pynvvideocodec-build.txt에 빌드 도구를 고정하고 docs/pynvvideocodec-build.md에 배포 절차를 기록한다. docs/reference/NvidiaDecode.html과 NvidiaEncode.html에도 수정 wheel 조건을 표시한다. 테스트는 패치 재현성·부호 있는 PTS·잠금 수명·지연과 재정렬·시간 기준 환산·인코더 통합 및 기존 회귀를 다룬다.

실제 빌드에서 scikit-build의 CMAKE_ARGS 중복 파싱과 Visual Studio 2026 미인식을 확인했다. tools/build_pynvvideocodec.py는 CMake 옵션을 SKBUILD_CONFIGURE_OPTIONS로 한 번만 전달하고 Windows 개발자 환경에서 Ninja Multi-Config를 기본 선택한다. 빌드 Python의 Scripts 경로를 하위 프로세스 PATH에 넣어 CMake·Ninja를 찾도록 한다. 이 동작은 tests/test_pynvvideocodec_build.py에서 공백 경로가 포함된 환경 변수 구성으로 검증한다.

## 2026-11-02 v141·CUDA 12.0 비교 빌드

FR-015~016에 따라 기존 패치와 빌드 도구를 그대로 사용한다. 새 작업 경로는 build/pynvvideocodec-patched-v141-cuda120, 출력은 dist/pynvvideocodec-patched-v141-cuda120이다. 원본 비교 빌드와 동일하게 MSVC 14.16.27023(컴파일러 19.16.27054), CUDA 12.0.140, Python 3.11.9, scikit-build 0.18.1, Ninja Multi-Config와 Release를 사용한다. 로컬 pybind11 2.10.0과 DLPack 0.8을 지정한다. 공식 wheel의 scikit-build 0.19.1과 차이가 남는다.

기존 준비 함수로 원본 해시·패치·로컬 버전을 검증하고 원본 비교 빌드 명령의 경로만 변경한다. 두 모듈을 별도 프로세스로 로드하여 GetLockedFrameWithPTS, 링커 14.16·PTX 8.0을 확인한다. 별도 설치 디렉터리를 사용해 기존 GPU 통합 검사를 수행하고, 산출물 해시·환경·대상 서버 미검증 상태를 validation.md와 docs/pynvvideocodec-build.md에 기록한다. 영상 처리 코드와 공개 계약은 변경하지 않는다. 헌장은 미작성 템플릿이며 추가 위반은 없다.

## 영구 v141·CUDA 12.0 진입점과 자동 다운로드

루트 build-pynvvideocodec.ps1을 build-pynvvideocodec-v141-cuda120.ps1로 교체한다. VsDevCmd를 자식 cmd에서 -vcvars_ver=14.16으로 실행한 환경을 가져오고 cl·link·nvcc 버전을 확인한다. CUDA 12.0·Ninja Multi-Config·Release·UTF-8을 명시하며 기존 외부 CMake 환경의 개입을 제거한다. 실행 후 호출자의 환경은 복원한다. 빌드 전용 Python 3.11 x64와 로컬 의존성을 기본 사용하고 -PrepareOnly와 사용자 경로를 지원한다.

Python 빌드 도구는 캐시를 먼저 검사하며 없는 ZIP만 NGC의 버전 고정 HTTPS 주소에서 임시 파일로 다운로드한다. 고정 해시가 일치해야 목적 경로로 교체하고 실패 시 임시 파일을 제거한다. 다운로드의 통신 오류를 명확한 빌드 오류로 변환한다. 기본 작업·출력은 검증된 patched-v141-cuda120 경로를 유지한다. 테스트는 통신을 대체하여 정상·손상·중단·캐시 재사용을 검증하고 새 PowerShell 진입점으로 실제 빌드한다.

삭제는 명시적인 실패 산출물 목록에만 적용한다. 모든 삭제 대상을 저장소 내부 절대 경로로 확인한 다음 PowerShell의 LiteralPath로 처리한다. 성공한 산출물과 참고용 원본은 유지한다. 문서는 새 방식 하나로 재작성하고 해시·로그·검증 결과를 남긴다.

삭제 실행이 자동 정책에 의해 거절된 경우를 위해 cleanup-pynvvideocodec-obsolete.ps1을 제공한다. 고정된 저장소 내부 대상만 선택하며 -WhatIf를 지원하고 연결 경로를 거부한다. 현재 실제 구형 산출물 삭제는 로컬 실행이 남아 있으며 이를 완료로 표시하지 않는다.
