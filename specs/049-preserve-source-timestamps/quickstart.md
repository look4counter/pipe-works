# 검증 안내

수정 wheel의 영구 빌드 진입점은 프로젝트 루트의 `build-pynvvideocodec-v141-cuda120.ps1`이다. 일반 PowerShell에서 실행하면 v141·CUDA 12.0을 선택하고, 없는 원본 ZIP은 공식 NGC에서 다운로드한 뒤 고정 해시를 확인한다. 도구·Python 준비와 경로 옵션은 [빌드 안내](../../docs/pynvvideocodec-build.md)를 따른다.

```powershell
./build-pynvvideocodec-v141-cuda120.ps1
./cleanup-pynvvideocodec-obsolete.ps1 -WhatIf
./cleanup-pynvvideocodec-obsolete.ps1
```

정리 스크립트는 실패한 CUDA 12.6 산출물만 처리한다. 이 세션에서는 자동 실행 정책에 의해 실제 삭제가 차단되어 사용자 로컬 실행이 필요하다. 성공한 v141 패치본과 원본 비교본은 유지한다.

생성된 `dist/pynvvideocodec-patched-v141-cuda120/pynvvideocodec-2.2.2+pipeworks.1-cp311-cp311-win_amd64.whl`을 설치하고 앱을 재시작한다. `NvidiaEncode(preserve_timestamps=True)`로 PTS 보존을 사용한다.

```powershell
$env:PYTHONPATH = 'src;tests'
.venv/Scripts/python.exe -m unittest test_pynvvideocodec_build
.venv/Scripts/python.exe -m unittest test_nvidia_decode.NativeDecodeTests.test_native_patched_locked_pts_survive_decode_and_reach_encoder
```

네이티브 검사는 수정 wheel과 CUDA 환경에서 건너뜀 없이 통과해야 한다. API 판별값 193·208을 별도 프로세스에서 지정하여 두 네이티브 모듈을 검증할 수 있다. 현재 작업의 검증용 실행 파일과 로그는 `build/pynvvideocodec-patched-v141-cuda120/verify-native.py`, `verify-121.log`, `verify-130.log`에 있다. 모듈 선택을 강제하는 것은 이전 드라이버나 vGPU 자체를 재현하는 것이 아니다. 대상 서버에서는 실제 입력으로 별도 확인한다.
