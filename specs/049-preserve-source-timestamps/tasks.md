# 작업 목록: 원본 타임스탬프 보존

## 1단계: 준비

- [X] T001 명세·설계·입력 계약 및 tests/test_nvidia_encode.py의 모의 인코더를 확인한다. FR-001~006.

## 2단계: 기반

- [X] T002 tests/test_nvidia_encode.py에 원본 시각·누락·지연·재생성·시간 기준 변경 검사를 추가하고 실패를 확인한다. FR-002~004, SC-001.

## 3단계: 사용자 이야기 1

- [X] T003 [US1] src/pipeworks/embedded/nvidia_encode.py에 옵션과 원본 시각 검증·시각 큐·메타데이터를 구현한다. FR-001~004.

## 4단계: 사용자 이야기 2

- [X] T004 [US2] tests/test_nvidia_encode.py에서 설정 우선순위·기본 모드·복구를 검증한다. FR-001, FR-005, SC-002.

## 5단계: 문서와 최종 검증

- [X] T005 docs/pipeworks/embedded/nvidia_encode.md와 docs/reference/NvidiaEncode.html에 사용법·상류 입력 조건·송출 보정 한계를 기록한다. FR-006.
- [X] T006 인코더·설정·RTSP 송출 회귀 검사와 수렴 점검을 수행한다. 결과는 specs/049-preserve-source-timestamps/validation.md에 기록한다. SC-001~002.

## 의존성과 실행 전략

T001 → T002 → T003 → T004 → T005 → T006 순서다. 같은 소스와 검증 계약을 다루므로 구현은 순차 수행한다. 최종 독립 테스트 모듈들은 함께 실행할 수 있다. 먼저 원본 보존을 완성하고 기본 동작과 문서를 검증한다.

## 6단계: 바인딩 빌드 확장 준비

- [X] T007 원본 ZIP과 빌드 도구 및 CMake 외부 의존성을 조사하고 tests/test_pynvvideocodec_build.py에 해시·추출·패치·버전 검증을 추가한다. FR-007, FR-012.
- [X] T008 tools/patches/pynvvideocodec-2.2.2-locked-frame-pts.patch와 tools/build_pynvvideocodec.py 및 build-pynvvideocodec.ps1을 추가한다. FR-007, FR-008, FR-012.

## 7단계: 무복사 PTS 전달

- [X] T009 tests/test_nvidia_decode.py에 API PTS·지연·재정렬·시간 기준 환산·큐 드롭·인코더 통합 검증을 추가하고 실패를 확인한다. FR-009, FR-010.
- [X] T010 src/pipeworks/embedded/nvidia_decode.py에 새 잠금 API와 PyAV 시간 기준 전달을 구현한다. FR-008~010.

## 8단계: 배포와 검증

- [X] T011 requirements-pynvvideocodec.txt와 docs/pipeworks/embedded/nvidia_decode.md 및 nvidia_encode.md, docs/pynvvideocodec-build.md에 빌드·설치·입출력 계약을 반영한다. FR-006, FR-011.
- [X] T012 수정 wheel 빌드를 시도하고 가능하면 별도 설치 디렉터리에서 네이티브 GPU 검증을 수행한다. 관련 회귀 검사 후 validation.md에 결과와 환경 제한을 기록하고 수렴 점검한다. FR-007~012.

추가 작업 순서: T007 → T008 → T009 → T010 → T011 → T012. 구현은 순차 수행하며 테스트 모듈 검사는 독립 실행할 수 있다.

## 9단계: 수렴 점검

- [X] T013 개발 의존성과 pybind11·DLPack 소스를 사용할 수 있는 빌드 환경에서 build-pynvvideocodec.ps1로 실제 wheel을 생성하고 별도 설치 환경에서 test_native_patched_locked_pts_survive_decode_and_reach_encoder를 실행하여 결과를 validation.md에 추가한다. FR-007~011, 계획의 네이티브 GPU 검증. 로컬 의존성으로 wheel 생성·설치 및 GPU 검증을 완료했다.

## 10단계: 실제 Windows 빌드 환경 보완

- [X] T014 tools/build_pynvvideocodec.py의 CMake 인자 전달과 Windows 개발자 환경 선택을 보완하고 tests/test_pynvvideocodec_build.py로 공백 경로 처리를 검증한 후 docs/pynvvideocodec-build.md에 재개 절차를 기록한다. FR-013. T013을 재실행하기 전에 수행한다.

## 11단계: 중복·역행 DTS 패킷 무시

- [X] T015 tests/test_rtsp_publish.py에 중복·역행·시간 기준 변경·정상 간격·PTS 재정렬 검사를 추가하고 기존 보정 기대값을 폐기 정책으로 변경하여 실패를 확인한다. FR-014.
- [X] T016 src/pipeworks/embedded/rtsp_publish.py의 비단조 DTS 보정을 폐기로 바꾸고 송신 성공 기준·연결 유지·입력 패킷 불변성을 검증한다. FR-014.
- [X] T017 docs/pipeworks/embedded/rtsp_publish.md와 nvidia_encode.md 및 docs/reference/NvidiaEncode.html을 갱신하고 송출·보고·복구·핫스왑 회귀 검사와 수렴 점검 결과를 validation.md에 기록한다. FR-006, FR-014.

실행 순서: T015 → T016 → T017.
